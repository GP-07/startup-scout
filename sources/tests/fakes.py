from sources.adapters.base import SourceAdapter, SourceFetchResult


class FakeSourceAdapter(SourceAdapter):
    def fetch_candidates(self, cursor):
        return SourceFetchResult(raw_startups=[], cursor=cursor)
