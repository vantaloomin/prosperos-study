import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from server.errors import DomainError
from server.providers.config import ProfileConfig
from server.providers.events import ProviderEvent
from server.providers.lmstudio_background import LMStudioBackground, unsupported
from server.providers.owned_prediction import UnconfirmedStop
from server.providers.scheduling import CLEANUP, WRITING, BackgroundInterrupted, work_scope
from server.providers.service import ProviderService


class Prediction:
    def __init__(self, *, short=False, acknowledge=True):
        self.short, self.acknowledge = short, acknowledge
        self.released = asyncio.Event()
        self.reason = 'eosFound'

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def __aiter__(self):
        yield SimpleNamespace(content='OK', reasoning_type='none')
        if not self.short:
            await self.released.wait()

    async def cancel(self):
        if self.acknowledge:
            self.reason = 'userStopped'
            self.released.set()

    def result(self):
        return SimpleNamespace(content='OK', model_info=SimpleNamespace(identifier='fixture'),
                               stats=SimpleNamespace(stop_reason=self.reason, prompt_tokens_count=3, predicted_tokens_count=1))


class Model:
    def __init__(self):
        self.calls = []
        self.acknowledge = True

    async def respond_stream(self, prompt, config):
        self.calls.append((prompt, config))
        return Prediction(short=prompt == 'Reply with OK.', acknowledge=self.acknowledge)


def configured(monkeypatch):
    config = ProfileConfig(provider='local', model='fixture', local_protocol='lmstudio').model_dump()
    model = Model()

    @asynccontextmanager
    async def loaded(_config):
        yield model
    monkeypatch.setattr('server.providers.lmstudio_background.loaded_model', loaded)
    return config, model, LMStudioBackground()


def test_verification_requires_acknowledged_stop_and_followup_and_expires(monkeypatch):
    config, model, background = configured(monkeypatch)
    assert not background.capability(config, None)['verified']
    receipt = asyncio.run(background.verify(config, None))
    assert receipt['verified'] and len(model.calls) == 2
    assert receipt['measurement']['stop_reason'] == 'userStopped'
    assert receipt['measurement']['followup_seconds'] >= 0
    assert not background.capability({**config, 'max_output_tokens': 1500}, None)['verified']
    for proof in background.verified.values():
        proof['expires'] = 0
    assert not background.capability(config, None)['verified']


def test_interruptible_stream_drains_to_ack_and_yields_instead_of_finishing_cleanup(monkeypatch):
    config, _, background = configured(monkeypatch)

    async def run():
        await background.verify(config, None)
        stop = asyncio.Event()
        with pytest.raises(BackgroundInterrupted):
            async for event in background.generate_interruptible(config, None, 'Instructions', 'Draft', stop):
                assert event.text == 'OK'
                stop.set()
    asyncio.run(run())


def test_missing_ack_revokes_verification(monkeypatch):
    config, model, background = configured(monkeypatch)

    async def run():
        await background.verify(config, None)
        monkeypatch.setattr('server.providers.owned_prediction.ACK_TIMEOUT', 0.05)
        model.acknowledge = False
        stop = asyncio.Event()
        with pytest.raises(UnconfirmedStop):
            async for _ in background.generate_interruptible(config, None, 'Instructions', 'Draft', stop):
                stop.set()
        assert not background.capability(config, None)['verified']
    asyncio.run(run())


def test_unsupported_settings_do_not_silently_change_protocol_or_call_model(monkeypatch):
    config, model, background = configured(monkeypatch)
    assert unsupported(config, 'credential')
    assert unsupported({**config, 'local_reasoning': 'off'}, None)
    assert unsupported({**config, 'base_url': 'https://localhost:1234/api/v1'}, None)
    with pytest.raises(DomainError):
        asyncio.run(background.verify(config, 'credential'))
    assert not model.calls


def test_repeated_cancellation_holds_shared_slot_until_server_ack(monkeypatch):
    config, model, background = configured(monkeypatch)

    async def run():
        await background.verify(config, None)
        prediction = Prediction(acknowledge=False)
        cancelled, visible, writer_started = asyncio.Event(), asyncio.Event(), asyncio.Event()

        async def cancel():
            prediction.reason = 'userStopped'
            cancelled.set()

        async def respond(*_args, **_kwargs):
            return prediction

        prediction.cancel = cancel
        model.respond_stream = respond

        class Http:
            async def generate(self, *_args):
                writer_started.set()
                yield ProviderEvent(text='Ready', done=True)

        service = ProviderService(None, http=Http())
        service.background = background

        async def consume(work):
            with work_scope(work):
                async for event in service.generate({'config': config}, 'Instruction', 'Synthetic input'):
                    if event.text:
                        visible.set()

        cleanup = asyncio.create_task(consume(CLEANUP))
        await asyncio.wait_for(visible.wait(), 1)
        cleanup.cancel()
        await asyncio.wait_for(cancelled.wait(), 1)
        cleanup.cancel()
        writer = asyncio.create_task(consume(WRITING))
        await asyncio.sleep(0)
        assert not writer_started.is_set() and len(service.scheduler.active) == 1
        prediction.released.set()
        await asyncio.gather(cleanup, return_exceptions=True)
        await writer
        assert writer_started.is_set() and not service.scheduler.active and not service.scheduler.blocked
    asyncio.run(run())


def test_failed_verification_stop_blocks_shared_resource(monkeypatch):
    config, model, background = configured(monkeypatch)
    monkeypatch.setattr('server.providers.owned_prediction.ACK_TIMEOUT', 0.05)
    model.acknowledge = False

    async def run():
        service = ProviderService(None)
        service.background = background
        profile = {'config': config}
        with pytest.raises(UnconfirmedStop):
            await service.verify_background(profile)
        assert service.background_capability(profile)['blocked']
        with pytest.raises(DomainError, match='did not acknowledge'):
            async for _ in service.generate(profile, 'Instruction', 'Input'):
                pytest.fail('The blocked inference slot was reused')
    asyncio.run(run())
