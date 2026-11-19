from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx

from sources.constants import HTTP_TIMEOUT_SECONDS, HTTP_USER_AGENT


@dataclass(frozen=True)
class RawStartup:
    """A startup as a source reports it, already mapped to our field names.

    `country` is an ISO 3166-1 alpha-2 code; adapters are responsible for converting it.
    """

    external_id: str
    url: str
    name: str
    website: str = ""
    description: str = ""
    country: str = ""
    city: str = ""
    raw_payload: dict = field(default_factory=dict)

    def mergeable_data(self):
        return {
            "name": self.name,
            "website": self.website,
            "description": self.description,
            "country": self.country,
            "city": self.city,
        }


@dataclass(frozen=True)
class SourceFetchResult:
    """What one run of an adapter found, and the cursor the next run starts from."""

    raw_startups: list
    cursor: dict


class SourceAdapter(ABC):
    """Port every source implements. Adapters only know how to read their own source."""

    # Whether the daily discovery task runs this source. Sources fed by hand set it to False.
    runs_periodically = True

    def __init__(self, config=None, http_client=None):
        self.config = config or {}
        self._http_client = http_client

    @property
    def http_client(self):
        """Created on first use, so adapters that never go to the network don't open one."""
        if self._http_client is None:
            self._http_client = httpx.Client(
                timeout=HTTP_TIMEOUT_SECONDS,
                headers={"User-Agent": HTTP_USER_AGENT},
            )
        return self._http_client

    @abstractmethod
    def fetch_candidates(self, cursor):
        """Return a `SourceFetchResult` with what was published after `cursor` ({} on first run)."""
