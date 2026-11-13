"""The queue at the door (app/door.py): never more requests inside than there are connections."""

import asyncio

from app.config import config
from app.db import engine
from app.door import WaitAtTheDoor


def test_no_more_than_the_places_are_inside_at_once():
    inside = most = 0

    async def slow_app(scope, receive, send):
        nonlocal inside, most
        inside += 1
        most = max(most, inside)
        await asyncio.sleep(0.01)
        inside -= 1

    door = WaitAtTheDoor(slow_app, places=3)

    async def ten_at_once():
        await asyncio.gather(*(door({"type": "http"}, None, None) for _ in range(10)))

    asyncio.run(ten_at_once())
    assert most == 3  # all 10 got in, never more than 3 at a time


def test_other_kinds_of_connection_go_straight_in():
    seen = []

    async def app(scope, receive, send):
        seen.append(scope["type"])

    asyncio.run(WaitAtTheDoor(app, places=1)({"type": "lifespan"}, None, None))
    assert seen == ["lifespan"]


def test_the_door_lets_in_as_many_as_the_database_has_connections():
    """If the pool had fewer connections than the door has places, the 5 pm deadlock could come back."""
    assert engine.pool.size() == config.db_connections
    assert engine.pool._max_overflow == 0
