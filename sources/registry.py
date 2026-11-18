"""In-memory mapping from a source key (stored in the database) to the adapter that reads it.

The database only stores the stable `Source.key`; class names never leave the code, so adapters
can be renamed or moved without touching stored data. Adapters are registered in phase 2.
"""

from sources.exceptions import UnknownSourceError

SOURCE_ADAPTERS = {}


def get_adapter(source):
    adapter_class = SOURCE_ADAPTERS.get(source.key)
    if adapter_class is None:
        raise UnknownSourceError(source.key)
    return adapter_class(config=source.config)
