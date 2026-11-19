"""In-memory mapping from a source key (stored in the database) to the adapter that reads it.

The database only stores the stable `Source.key`; class names never leave the code, so adapters
can be renamed or moved without touching stored data.
"""

from sources.adapters.hacker_news import HackerNewsAdapter
from sources.adapters.hacker_news_hiring import HackerNewsHiringAdapter
from sources.adapters.manual import ManualSourceAdapter
from sources.constants import SourceKey
from sources.exceptions import UnknownSourceError

SOURCE_ADAPTERS = {
    SourceKey.HACKER_NEWS: HackerNewsAdapter,
    SourceKey.HACKER_NEWS_HIRING: HackerNewsHiringAdapter,
    SourceKey.MANUAL: ManualSourceAdapter,
}


def get_adapter(source):
    adapter_class = SOURCE_ADAPTERS.get(source.key)
    if adapter_class is None:
        raise UnknownSourceError(source.key)
    return adapter_class(config=source.config)


def runs_periodically(source):
    adapter_class = SOURCE_ADAPTERS.get(source.key)
    return adapter_class is not None and adapter_class.runs_periodically
