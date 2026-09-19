import asyncio
from types import SimpleNamespace

import pytest

from server.providers.owned_prediction import UnconfirmedStop, acknowledged_prediction


class Prediction:
    def __init__(self, acknowledge=True):
        self.started = asyncio.Event()
        self.stopped = asyncio.Event()
        self.release = asyncio.Event()
        self.acknowledge = acknowledge

    async def __aenter__(self):
        self.started.set()
        return self

    async def __aexit__(self, *_):
        pass

    async def __aiter__(self):
        yield SimpleNamespace(content='one', reasoning_type='none')
        await self.release.wait()

    async def cancel(self):
        assert self.started.is_set()
        self.stopped.set()
        if self.acknowledge:
            self.release.set()

    def result(self):
        assert self.release.is_set()
        return SimpleNamespace(stats=SimpleNamespace(stop_reason='userStopped'))


def test_probe_requires_terminal_acknowledgement_after_a_real_fragment():
    async def run():
        prediction, events = Prediction(), []
        result, timing = await acknowledged_prediction(prediction, asyncio.Event(), events.append, 1, stop_after_fragment=True)
        assert prediction.stopped.is_set() and result.stats.stop_reason == 'userStopped'
        assert timing['cancellation_seconds'] >= 0 and timing['cancelled']
        assert events[0].text == 'one'
    asyncio.run(run())


def test_stop_before_dispatch_still_waits_for_started_channel():
    async def run():
        stop = asyncio.Event()
        stop.set()
        prediction = Prediction()
        _, timing = await acknowledged_prediction(prediction, stop, lambda _: None, 1)
        assert timing['cancelled'] and prediction.stopped.is_set()
    asyncio.run(run())


def test_missing_acknowledgement_is_not_treated_as_cancellation_success(monkeypatch):
    monkeypatch.setattr('server.providers.owned_prediction.ACK_TIMEOUT', 0.01)

    async def run():
        with pytest.raises(UnconfirmedStop):
            await acknowledged_prediction(Prediction(False), asyncio.Event(), lambda _: None, 1, stop_after_fragment=True)
    asyncio.run(run())


def test_broken_reader_and_stuck_cancel_do_not_establish_termination(monkeypatch):
    monkeypatch.setattr('server.providers.owned_prediction.ACK_TIMEOUT', 0.02)

    class BrokenReader(Prediction):
        async def __aiter__(self):
            yield SimpleNamespace(content='one', reasoning_type='none')
            raise ConnectionError('Lost the terminal acknowledgement')

    class StuckCancel(Prediction):
        async def cancel(self):
            await asyncio.Event().wait()

    async def run():
        for prediction in [BrokenReader(), StuckCancel()]:
            with pytest.raises(UnconfirmedStop):
                await acknowledged_prediction(prediction, asyncio.Event(), lambda _: None, 1, stop_after_fragment=True)
    asyncio.run(run())
