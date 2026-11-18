class InvalidWebsiteError(ValueError):
    """The value has no registrable domain (empty, IP address, localhost, malformed...)."""

    def __init__(self, website):
        self.website = website
        super().__init__(f"'{website}' has no registrable domain")


class IngestionConflictError(Exception):
    """The startup could not be ingested after retrying concurrent unique-constraint conflicts."""

    def __init__(self, source_key, external_id):
        self.source_key = source_key
        self.external_id = external_id
        super().__init__(f"Could not ingest {source_key}:{external_id} after concurrent conflicts")
