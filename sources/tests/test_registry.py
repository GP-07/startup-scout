from unittest import mock

import pytest

from sources import registry
from sources.constants import SourceKey
from sources.exceptions import UnknownSourceError
from sources.models import Source
from sources.tests.fakes import FakeSourceAdapter

pytestmark = pytest.mark.django_db


def test_initial_sources_are_seeded_by_migration():
    assert set(Source.objects.values_list("key", flat=True)) == {
        SourceKey.HACKER_NEWS,
        SourceKey.STARTUPXPLORE,
        SourceKey.MANUAL,
    }


def test_get_adapter_builds_adapter_mapped_to_source_key_with_its_config():
    source = Source.objects.get(key=SourceKey.HACKER_NEWS)
    source.config = {"tags": ["show_hn"]}

    with mock.patch.dict(registry.SOURCE_ADAPTERS, {SourceKey.HACKER_NEWS: FakeSourceAdapter}):
        adapter = registry.get_adapter(source)

    assert isinstance(adapter, FakeSourceAdapter)
    assert adapter.config == {"tags": ["show_hn"]}


def test_get_adapter_raises_for_key_without_adapter():
    source = Source(key="not_registered", name="Not registered")

    with pytest.raises(UnknownSourceError):
        registry.get_adapter(source)
