import asyncio

import pytest

from server.errors import DomainError
from server.providers.config import ProfileConfig
from server.providers.scheduling import CLEANUP, WRITING, RequestScheduler, Work, resource_for


def local(**options):
    return ProfileConfig(provider='local', model='fixture', **options).model_dump()


def test_local_aliases_share_one_resource_and_explicit_hardware_can_be_independent():
    assert resource_for(local()) == resource_for(local(base_url='http://localhost:5001/api/v1'))
    assert resource_for(local()) == resource_for(ProfileConfig(provider='compatible', model='fixture', base_url='http://127.0.0.1:9999/v1').model_dump())
    assert resource_for(local(resource_group='second GPU')) != resource_for(local())


def test_foreground_overtakes_waiting_helpers_and_cancelled_waiter_leaves_no_slot():
    async def run():
        scheduler, order = RequestScheduler(), []

        async def job(name, work):
            async with scheduler.reserve(local(), work):
                order.append(name)

        async with scheduler.reserve(local(), WRITING):
            helper = asyncio.create_task(job('helper', Work()))
            removed = asyncio.create_task(job('removed', Work()))
            writer = asyncio.create_task(job('writer', WRITING))
            await asyncio.sleep(0)
            removed.cancel()
            await asyncio.gather(removed, return_exceptions=True)
        await asyncio.gather(helper, writer)
        assert order == ['writer', 'helper']
        assert not scheduler.active and not scheduler.waiting
    asyncio.run(run())


def test_interruption_signal_does_not_release_resource_before_acknowledgement():
    async def run():
        scheduler, released, entered = RequestScheduler(), asyncio.Event(), asyncio.Event()

        async def writer():
            async with scheduler.reserve(local(), WRITING):
                entered.set()

        async with scheduler.reserve(local(), CLEANUP) as cleanup:
            task = asyncio.create_task(writer())
            await cleanup.stop.wait()
            assert not entered.is_set()
            released.set()  # transport acknowledges release before leaving the lease
        await task
        assert released.is_set() and entered.is_set()
    asyncio.run(run())


def test_foreground_preparation_prevents_optional_admission_and_resources_overlap():
    async def run():
        scheduler, entered = RequestScheduler(), []

        async def background():
            async with scheduler.reserve(local(), CLEANUP):
                entered.append('background')

        with scheduler.foreground_work():
            task = asyncio.create_task(background())
            await asyncio.sleep(0)
            assert not entered
            async with scheduler.reserve(local(resource_group='independent GPU'), WRITING):
                assert len(scheduler.active) == 1
        await task
        assert entered == ['background']
    asyncio.run(run())


def test_unconfirmed_release_blocks_waiting_and_new_requests():
    async def run():
        scheduler = RequestScheduler()
        async with scheduler.reserve(local(), CLEANUP) as lease:
            scheduler.block(lease.resource, 'Stop not acknowledged')
        with pytest.raises(DomainError, match='Stop not acknowledged'):
            async with scheduler.reserve(local(), WRITING):
                pytest.fail('A blocked resource was reused')
    asyncio.run(run())


def test_cancelled_waiter_is_ignored_before_its_finalizer_runs():
    async def run():
        scheduler = RequestScheduler()

        async def waiting():
            async with scheduler.reserve(local(), WRITING):
                pytest.fail('Cancelled work was admitted')

        async with scheduler.reserve(local(), WRITING):
            task = asyncio.create_task(waiting())
            await asyncio.sleep(0)
            task.cancel()
            # The occupied lease exits and dispatches before task.finally executes.
        await asyncio.gather(task, return_exceptions=True)
        assert not scheduler.active and not scheduler.waiting
    asyncio.run(run())
