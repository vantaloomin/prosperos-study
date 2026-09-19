"""Opt-in, verified LM Studio SDK cancellation for otherwise ordinary model jobs."""
import asyncio
import hashlib
import json
import time
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from server.errors import DomainError, require
from server.providers.owned_prediction import (
    UnconfirmedStop,
    acknowledged_prediction,
    checked_result,
)

VERIFICATION_SECONDS = 1800


def fingerprint(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()


def unsupported(config, key):
    if config['provider'] != 'local' or config.get('local_protocol') != 'lmstudio':
        return 'Reading-time inference currently requires an LM Studio native profile.'
    if key or urlsplit(config['base_url']).scheme != 'http':
        return 'This SDK stop protocol currently supports local HTTP connections without API authentication.'
    if config.get('local_reasoning') is not None:
        return 'Use model-default local reasoning for this SDK protocol; explicit reasoning overrides remain supported before ready.'
    return ''


@asynccontextmanager
async def loaded_model(config):
    import lmstudio as lms
    async with lms.AsyncClient(urlsplit(config['base_url']).netloc) as client:
        matches = []
        for model in await client.llm.list_loaded():
            info = await model.get_info()
            if config['model'] in {model.identifier, info.model_key}:
                matches.append(model)
        require(len(matches) == 1, 'Load exactly one instance of this saved model in LM Studio, then verify interruption.', 409)
        yield matches[0]


def prediction_config(config, *, probe=False):
    values = {'maxTokens': min(config['max_output_tokens'], 128 if probe else 1200),
              'contextOverflowPolicy': 'stopAtLimit'}
    if config.get('temperature') is not None:
        values['temperature'] = config['temperature']
    return values


async def drain_owner(owner):
    # Repeated Stop/disable/shutdown signals must not abandon the server ack.
    while True:
        try:
            return await asyncio.shield(owner)
        except asyncio.CancelledError:
            if owner.done():
                raise UnconfirmedStop() from None


class LMStudioBackground:
    def __init__(self):
        self.verified = {}

    def capability(self, config, key):
        reason = unsupported(config, key)
        proof = self.verified.get(fingerprint(config))
        valid = not reason and proof is not None and time.monotonic() < proof['expires']
        return {'supported': not bool(reason), 'verified': valid,
                'reason': reason or ('Interruption verified for this app session and profile.' if valid else
                                    'Verify interruption with two short test requests before using reading-time inference.'),
                'measurement': proof['measurement'] if valid else None}

    def revoke(self, config):
        self.verified.pop(fingerprint(config), None)

    async def verify(self, config, key):
        require(not unsupported(config, key), unsupported(config, key), 409)
        self.revoke(config)
        async with asyncio.timeout(min(config['timeout_seconds'], 60)), loaded_model(config) as model:
            prediction = await model.respond_stream('Count upward from one, one number per line, until stopped.',
                                                    config=prediction_config(config, probe=True))
            result, measurement = await acknowledged_prediction(prediction, asyncio.Event(), lambda _: None,
                                                                 min(config['timeout_seconds'], 45), stop_after_fragment=True)
            require(measurement['cancelled'] and result.stats.stop_reason == 'userStopped',
                    'The probe finished without an acknowledged user stop. Interruption was not verified.', 409)
            probe = await model.respond_stream('Reply with OK.', config={'maxTokens': 16, 'contextOverflowPolicy': 'stopAtLimit'})
            followup, followup_timing = await acknowledged_prediction(probe, asyncio.Event(), lambda _: None, 10)
            require(not followup_timing['cancelled'] and bool(followup.content.strip()),
                    'The stopped request was acknowledged, but the follow-up probe did not complete.', 409)
            measurement['followup_seconds'] = followup_timing['prediction_seconds']
        self.verified[fingerprint(config)] = {'expires': time.monotonic() + VERIFICATION_SECONDS, 'measurement': measurement}
        return self.capability(config, key)

    async def generate_interruptible(self, config, key, prompt, content, stop):
        require(self.capability(config, key)['verified'], 'Verify interruption for this profile first.', 409)
        queue = asyncio.Queue()
        owner = asyncio.create_task(self.owned(config, prompt, content, stop, queue))
        try:
            while (event := await queue.get()) is not None:
                yield event
            yield await owner
        finally:
            stop.set()
            try:
                await drain_owner(owner)
            except UnconfirmedStop:
                self.revoke(config)
                raise
            except DomainError:
                pass

    async def owned(self, config, prompt, content, stop, queue):
        import lmstudio as lms
        try:
            async with asyncio.timeout(config['timeout_seconds'] + 5), loaded_model(config) as model:
                require(not stop.is_set(), 'Background work stopped before dispatch.', 409)
                chat = lms.Chat(prompt)
                chat.add_user_message(content)
                prediction = await model.respond_stream(chat, config=prediction_config(config))
                try:
                    result, timing = await acknowledged_prediction(prediction, stop, queue.put_nowait, config['timeout_seconds'])
                except (DomainError, asyncio.CancelledError):
                    raise
                except Exception as error:
                    raise UnconfirmedStop() from error
                return checked_result(result, timing)
        finally:
            queue.put_nowait(None)
