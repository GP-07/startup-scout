class UnknownSourceError(Exception):
    """A source stored in the database has no adapter registered in memory."""

    def __init__(self, source_key):
        self.source_key = source_key
        super().__init__(f"No adapter registered for source key '{source_key}'")


class SourceFetchError(Exception):
    """A source could not be read (network error, unexpected response, bad config)."""
