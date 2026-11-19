from unittest import mock

import pytest

from sources import registry
from sources.adapters.hacker_news import HackerNewsAdapter
from sources.adapters.hacker_news_hiring import HackerNewsHiringAdapter
from sources.adapters.manual import ManualSourceAdapter
from sources.constants import SourceKey
from sources.exceptions import UnknownSourceError
from sources.models import Source
from sources.tests.fakes import FakeSourceAdapter

pytestmark = pytest.mark.django_db


def test_initial_sources_are_seeded_by_migration():
    assert set(Source.objects.values_list("key", flat=True)) == {
        SourceKey.HACKER_NEWS,
        SourceKey.HACKER_NEWS_HIRING,
        SourceKey.MANUAL,
    }


def test_every_enabled_source_has_an_adapter():
    for source in Source.objects.filter(enabled=True):
        assert source.key in registry.SOURCE_ADAPTERS, source.key


def test_registered_adapters():
    expected_adapters = {
        SourceKey.HACKER_NEWS: HackerNewsAdapter,
        SourceKey.HACKER_NEWS_HIRING: HackerNewsHiringAdapter,
        SourceKey.MANUAL: ManualSourceAdapter,
    }

    assert dict(registry.SOURCE_ADAPTERS) == expected_adapters


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


def test_runs_periodically_depends_on_adapter():
    assert registry.runs_periodically(Source.objects.get(key=SourceKey.HACKER_NEWS)) is True
    assert registry.runs_periodically(Source.objects.get(key=SourceKey.MANUAL)) is False
    assert registry.runs_periodically(Source(key="not_registered")) is False
