"""A queue at the door: only as many requests inside at once as there are database connections.

Why: the routes are plain `def`, so FastAPI runs each one on a worker thread,
up to 40 at once. A request holds its database connection from its first query
until its session is closed, and that is AFTER FastAPI has checked the answer,
which needs a worker thread too.

The load test (loadtest/run.py) showed what happens at 5 pm, when hundreds of
students arrive at the same moment:

    40 threads are taken by new requests, all waiting for a connection.
    The 15 requests that HAVE connections have finished their work, but are
    waiting for a free thread to check their answer.
    Nobody can move. After 30 seconds the waiting requests give up with an
    error, and the next wave does the same.

0 of 370 students could log in. With this queue, at most 15 requests are inside
at once, so every one of them can always get a connection and finish. The others
wait in line on the event loop, which costs no thread and no connection, usually
for a few milliseconds.
"""

import asyncio
import weakref


class WaitAtTheDoor:
    def __init__(self, app, places: int):
        self.app = app
        self.places = places
        # One queue per event loop. The server has one; the tests start a new one for each test client.
        self._doors: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        loop = asyncio.get_running_loop()
        door = self._doors.get(loop)
        if door is None:
            door = self._doors[loop] = asyncio.Semaphore(self.places)
        async with door:
            await self.app(scope, receive, send)
