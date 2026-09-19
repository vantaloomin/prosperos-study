from contextlib import contextmanager
from contextvars import ContextVar

from server.database import now

RECEIVED = ContextVar('writing_request_received', default=None)


@contextmanager
def writing_clock():
    token = RECEIVED.set(now())
    try:
        yield
    finally:
        RECEIVED.reset(token)
