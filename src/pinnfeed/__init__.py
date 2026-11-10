"""PinnFeed: real-time Pinnacle odds API client (REST + WebSocket). https://pinnfeed.io"""
from ._version import __version__
from .client import AsyncPinnFeed, PinnFeed, filter_params
from .errors import AuthenticationError, NotFoundError, PinnFeedError, PlanError, RateLimitError
from .stream import OddsBook, PinnFeedStream

__all__ = [
    "__version__", "PinnFeed", "AsyncPinnFeed", "PinnFeedStream", "OddsBook", "filter_params",
    "PinnFeedError", "AuthenticationError", "PlanError", "RateLimitError", "NotFoundError",
]
