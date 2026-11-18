from sources.adapters.base import SourceAdapter


class FakeSourceAdapter(SourceAdapter):
    def fetch_candidates(self, since=None):
        return []
