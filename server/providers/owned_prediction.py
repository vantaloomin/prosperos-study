"""Keep the inference lease until an owned prediction acknowledges termination."""
import asyncio
import time

from server.errors import DomainError, require
from server.providers.events import ProviderEvent
from server.providers.scheduling import BackgroundInterrupted

ACK_TIMEOUT = 5.0


class UnconfirmedStop(DomainError):
    def __init__(self):
        super().__init__('The model did not acknowledge stopping. Restart the local model server, '
                         'then reset its interruption check in model settings before generating again.', 409)


async def prediction_events(prediction, started, publish):
    async with prediction:
        started.set()
        async for fragment in prediction:
            if fragment.reasoning_type == 'none':
                publish(ProviderEvent(text=fragment.content))
            elif fragment.content:
                publish(ProviderEvent(usage={'reasoning_received': True}))
        result = prediction.result()
    return result


async def interruption_signal(started, signal):
    await started.wait()
    await signal.wait()


async def stop_prediction(prediction, reader):
    try:
        async with asyncio.timeout(ACK_TIMEOUT):
            await prediction.cancel()
            return await asyncio.shield(reader)
    except Exception as error:
        raise UnconfirmedStop() from error


async def acknowledged_prediction(prediction, stop, publish, timeout, *, stop_after_fragment=False):
    """The SDK reader stays alive after cancel, so server stats acknowledge release."""
    started = time.perf_counter()
    first = asyncio.Event()
    dispatched = asyncio.Event()

    def receive(event):
        publish(event)
        first.set()

    reader = asyncio.create_task(prediction_events(prediction, dispatched, receive))
    signal = asyncio.create_task(interruption_signal(dispatched, first if stop_after_fragment else stop))
    try:
        done, _ = await asyncio.wait({reader, signal}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
        if reader in done:
            return reader.result(), {'prediction_seconds': time.perf_counter() - started, 'cancelled': False}
        cancel_started = time.perf_counter()
        result = await stop_prediction(prediction, reader)
        timing = {'prediction_seconds': time.perf_counter() - started,
                  'cancellation_seconds': time.perf_counter() - cancel_started,
                  'stop_reason': result.stats.stop_reason, 'cancelled': True}
        if not done:
            raise DomainError('The background request reached its saved time limit. The original is available.', 504)
        return result, timing
    except asyncio.CancelledError:
        await stop_prediction(prediction, reader)
        raise
    except DomainError:
        raise
    except Exception as error:
        # A broken reader or stop channel does not establish server termination.
        raise UnconfirmedStop() from error
    finally:
        signal.cancel()
        if not reader.done():
            reader.cancel()
        await asyncio.gather(signal, reader, return_exceptions=True)


def checked_result(result, timing):
    if timing['cancelled']:
        raise BackgroundInterrupted()
    require(result.stats.stop_reason in {'eosFound', 'stopStringFound'},
            'Background output ended before a complete response. The original is available.', 502)
    return ProviderEvent(done=True, model=result.model_info.identifier,
                         usage={'input_tokens': result.stats.prompt_tokens_count,
                                'output_tokens': result.stats.predicted_tokens_count,
                                'background_timing': timing})
