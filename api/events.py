"""Event Bus — publish/subscribe model for play events."""
import logging
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)

PlayEventHandler = Callable[[int, dict], Awaitable[None]]

_subscribers: list[PlayEventHandler] = []


def subscribe(handler: PlayEventHandler):
    """Register a handler to receive play events."""
    _subscribers.append(handler)


def unsubscribe(handler: PlayEventHandler):
    """Remove a handler."""
    _subscribers.remove(handler)


async def publish_play_event(user_id: int, play_data: dict):
    """Publish a play event to all subscribers. Each handler is independent."""
    for handler in _subscribers:
        try:
            await handler(user_id, play_data)
        except Exception as e:
            logger.error(f"Event handler {handler.__name__} failed: {e}")
