from abc import ABC, abstractmethod
from dataclasses import dataclass, field


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


class SourceAdapter(ABC):
    """Port every source implements. Adapters only know how to read their own source."""

    def __init__(self, config=None):
        self.config = config or {}

    @abstractmethod
    def fetch_candidates(self, since=None):
        """Return the list of `RawStartup` published since the given cursor."""
