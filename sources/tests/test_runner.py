from unittest import mock

import pytest

from sources import registry
from sources.adapters.base import RawStartup, SourceAdapter, SourceFetchResult
from sources.constants import SourceKey, SourceRunStatus
from sources.exceptions import SourceFetchError
from sources.models import Source, SourceRun
from sources.runner import SourceRunner
from startups.ingestion import StartupIngestionService
from startups.models import Startup
from startups.tests.fakes import FakeRedirectResolver

pytestmark = pytest.mark.django_db


class StaticSourceAdapter(SourceAdapter):
    """Returns two startups and remembers the cursor it was called with."""

    received_cursors = []

    def fetch_candidates(self, cursor):
        StaticSourceAdapter.received_cursors.append(cursor)
        return SourceFetchResult(
            raw_startups=[
                RawStartup(external_id="1", url="", name="Acme", website="https://acme.com"),
                RawStartup(external_id="2", url="", name="Brisa", website="https://brisa.com"),
            ],
            cursor={"last_created_at_i": 200},
        )


class BrokenSourceAdapter(SourceAdapter):
    def fetch_candidates(self, cursor):
        raise SourceFetchError("API down")


def build_runner():
    return SourceRunner(
        ingestion_service=StartupIngestionService(redirect_resolver=FakeRedirectResolver())
    )


def hacker_news_source():
    return Source.objects.get(key=SourceKey.HACKER_NEWS)


def test_successful_run_ingests_candidates_and_stores_cursor():
    with mock.patch.dict(registry.SOURCE_ADAPTERS, {SourceKey.HACKER_NEWS: StaticSourceAdapter}):
        source_run = build_runner().run(hacker_news_source())

    assert source_run.status == SourceRunStatus.SUCCEEDED
    assert source_run.items_seen == 2
    assert source_run.items_new == 2
    assert source_run.cursor == {"last_created_at_i": 200}
    assert source_run.finished_at is not None
    assert Startup.objects.count() == 2


def test_next_run_starts_from_last_successful_cursor_and_counts_only_new_startups():
    StaticSourceAdapter.received_cursors.clear()
    with mock.patch.dict(registry.SOURCE_ADAPTERS, {SourceKey.HACKER_NEWS: StaticSourceAdapter}):
        build_runner().run(hacker_news_source())
        second_run = build_runner().run(hacker_news_source())

    assert StaticSourceAdapter.received_cursors == [{}, {"last_created_at_i": 200}]
    assert second_run.items_seen == 2
    assert second_run.items_new == 0


def test_failed_fetch_marks_run_as_failed_and_keeps_previous_cursor():
    SourceRun.objects.create(
        source=hacker_news_source(),
        status=SourceRunStatus.SUCCEEDED,
        cursor={"last_created_at_i": 100},
    )

    with mock.patch.dict(registry.SOURCE_ADAPTERS, {SourceKey.HACKER_NEWS: BrokenSourceAdapter}):
        source_run = build_runner().run(hacker_news_source())

    assert source_run.status == SourceRunStatus.FAILED
    assert "API down" in source_run.error
    assert source_run.cursor == {}
    assert SourceRun.objects.filter(status=SourceRunStatus.SUCCEEDED).count() == 1


def test_one_failing_startup_does_not_stop_the_run():
    service = StartupIngestionService(redirect_resolver=FakeRedirectResolver())
    runner = SourceRunner(ingestion_service=service)
    original_ingest = service.ingest
    calls = []

    with (
        mock.patch.dict(registry.SOURCE_ADAPTERS, {SourceKey.HACKER_NEWS: StaticSourceAdapter}),
        mock.patch.object(
            service,
            "ingest",
            side_effect=[RuntimeError("boom"), mock.DEFAULT],
            wraps=original_ingest,
        ) as ingest_mock,
    ):
        source_run = runner.run(hacker_news_source())
        calls = ingest_mock.call_args_list

    assert len(calls) == 2
    assert source_run.status == SourceRunStatus.SUCCEEDED
    assert source_run.items_new == 1
    assert "boom" in source_run.error
