import threading

import pytest
from django.db import connection

from sources.constants import SourceKey
from sources.models import Source, SourceRecord
from startups.ingestion import StartupIngestionService
from startups.models import Startup, StartupDomain
from startups.tests.fakes import FakeRedirectResolver, build_raw_startup

THREAD_COUNT = 4


class ConcurrentIngestion:
    """Runs several ingestions of the same startup at the same moment, one per thread."""

    def __init__(self, raw_startups_by_source_key):
        self.raw_startups_by_source_key = raw_startups_by_source_key
        self.barrier = threading.Barrier(len(raw_startups_by_source_key))
        self.errors = []

    def run(self):
        threads = [
            threading.Thread(target=self.ingest, args=(source_key, raw_startup))
            for source_key, raw_startup in self.raw_startups_by_source_key
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    def ingest(self, source_key, raw_startup):
        try:
            source = Source.objects.get(key=source_key)
            service = StartupIngestionService(redirect_resolver=FakeRedirectResolver())
            self.barrier.wait()
            service.ingest(source, raw_startup)
        except Exception as error:  # noqa: BLE001 - collected and asserted by the test
            self.errors.append(error)
        finally:
            connection.close()


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_concurrent_ingestion_of_same_domain_creates_one_startup():
    ingestion = ConcurrentIngestion(
        [
            (SourceKey.HACKER_NEWS, build_raw_startup("hn-1", "Acme", website="https://acme.com")),
            (SourceKey.STARTUPXPLORE, build_raw_startup("acme", "Acme", website="acme.com")),
            (SourceKey.MANUAL, build_raw_startup("manual-1", "Acme", website="www.acme.com")),
            (
                SourceKey.HACKER_NEWS,
                build_raw_startup("hn-2", "Acme", website="https://acme.com/x"),
            ),
        ]
    )

    ingestion.run()

    assert ingestion.errors == []
    assert Startup.objects.count() == 1
    assert StartupDomain.objects.count() == 1
    assert SourceRecord.objects.count() == THREAD_COUNT


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_concurrent_ingestion_of_same_record_creates_it_once():
    raw_startup = build_raw_startup("hn-1", "Acme", website="https://acme.com")
    ingestion = ConcurrentIngestion(
        [(SourceKey.HACKER_NEWS, raw_startup) for _ in range(THREAD_COUNT)]
    )

    ingestion.run()

    assert ingestion.errors == []
    assert Startup.objects.count() == 1
    assert SourceRecord.objects.count() == 1
