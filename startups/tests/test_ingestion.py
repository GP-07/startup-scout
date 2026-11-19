import pytest

from sources.constants import SourceKey
from sources.models import Source, SourceRecord
from startups.ingestion import StartupIngestionService
from startups.models import Startup, StartupDomain
from startups.tests.fakes import FakeRedirectResolver, build_raw_startup

pytestmark = pytest.mark.django_db


def get_source(key):
    return Source.objects.get(key=key)


def build_service(final_urls=None):
    return StartupIngestionService(redirect_resolver=FakeRedirectResolver(final_urls))


def test_ingest_creates_startup_with_domain_and_source_record():
    service = build_service()

    result = service.ingest(
        get_source(SourceKey.HACKER_NEWS),
        build_raw_startup("hn-1", "Acme", website="https://www.acme.com", description="Robots"),
    )

    assert result.created is True
    assert result.record_created is True
    startup = result.startup
    assert startup.name == "Acme"
    assert startup.website == "https://www.acme.com"
    assert startup.description == "Robots"
    assert list(startup.domains.values_list("domain", "is_primary")) == [("acme.com", True)]
    assert startup.source_records.count() == 1


def test_same_domain_from_two_sources_is_one_startup():
    service = build_service()
    service.ingest(
        get_source(SourceKey.HACKER_NEWS),
        build_raw_startup("hn-1", "Acme", website="https://acme.com"),
    )

    result = service.ingest(
        get_source(SourceKey.MANUAL),
        build_raw_startup("acme", "Acme S.L.", website="https://www.acme.com/es/"),
    )

    assert result.created is False
    assert result.record_created is True
    assert Startup.objects.count() == 1
    assert SourceRecord.objects.filter(startup=result.startup).count() == 2


def test_subdomain_and_www_variants_are_deduplicated():
    service = build_service()
    service.ingest(
        get_source(SourceKey.HACKER_NEWS),
        build_raw_startup("hn-1", "Acme", website="https://app.acme.com/signup"),
    )
    service.ingest(
        get_source(SourceKey.MANUAL),
        build_raw_startup("acme", "Acme", website="http://WWW.ACME.COM"),
    )

    assert Startup.objects.count() == 1


def test_paas_subdomains_are_different_startups():
    service = build_service()
    service.ingest(
        get_source(SourceKey.HACKER_NEWS),
        build_raw_startup("hn-1", "Foo", website="https://foo.vercel.app"),
    )
    service.ingest(
        get_source(SourceKey.HACKER_NEWS),
        build_raw_startup("hn-2", "Bar", website="https://bar.vercel.app"),
    )

    assert Startup.objects.count() == 2


def test_redirect_target_is_stored_as_alias_and_used_for_matching():
    service = build_service(final_urls={"https://acme.io": "https://www.acme.com/"})
    first = service.ingest(
        get_source(SourceKey.HACKER_NEWS),
        build_raw_startup("hn-1", "Acme", website="https://acme.io"),
    )

    second = service.ingest(
        get_source(SourceKey.MANUAL),
        build_raw_startup("acme", "Acme", website="https://acme.com"),
    )

    assert second.startup == first.startup
    domains = dict(first.startup.domains.values_list("domain", "is_primary"))
    assert domains == {"acme.com": True, "acme.io": False}


def test_reingesting_same_record_updates_it_without_duplicates():
    service = build_service()
    source = get_source(SourceKey.HACKER_NEWS)
    service.ingest(source, build_raw_startup("hn-1", "Acme", website="https://acme.com"))

    result = service.ingest(
        source,
        build_raw_startup("hn-1", "Acme", website="https://acme.com", description="Updated"),
    )

    assert result.created is False
    assert result.record_created is False
    assert SourceRecord.objects.count() == 1
    assert result.startup.description == "Updated"


def test_fields_are_merged_by_source_priority():
    service = build_service()
    service.ingest(
        get_source(SourceKey.HACKER_NEWS),
        build_raw_startup("hn-1", "Acme (Show HN)", website="https://acme.com", description="HN"),
    )

    result = service.ingest(
        get_source(SourceKey.MANUAL),
        build_raw_startup(
            "acme",
            "Acme",
            website="https://acme.com",
            description="Manual",
            country="ES",
            city="Barcelona",
        ),
    )

    startup = result.startup
    assert startup.name == "Acme"
    assert startup.description == "Manual"
    assert startup.country == "ES"
    assert startup.city == "Barcelona"
    assert startup.field_sources["name"] == SourceKey.MANUAL


def test_startup_without_website_and_same_name_is_flagged_not_merged():
    service = build_service()
    existing = service.ingest(
        get_source(SourceKey.MANUAL),
        build_raw_startup("acme", "Acme S.L.", website="https://acme.com"),
    ).startup

    result = service.ingest(
        get_source(SourceKey.HACKER_NEWS),
        build_raw_startup("hn-9", "ACME"),
    )

    assert result.created is True
    assert Startup.objects.count() == 2
    assert result.startup.possible_duplicate_of == existing
    assert not result.startup.domains.exists()


def test_invalid_website_is_ingested_as_startup_without_domain():
    service = build_service()

    result = service.ingest(
        get_source(SourceKey.HACKER_NEWS),
        build_raw_startup("hn-1", "Local thing", website="http://localhost:3000"),
    )

    assert result.created is True
    assert not StartupDomain.objects.exists()


def test_domains_split_across_two_startups_are_flagged_as_duplicates():
    service = build_service()
    acme_io = service.ingest(
        get_source(SourceKey.HACKER_NEWS),
        build_raw_startup("hn-1", "Acme Labs", website="https://acme.io"),
    ).startup
    acme_com = service.ingest(
        get_source(SourceKey.HACKER_NEWS),
        build_raw_startup("hn-2", "Acme Robotics", website="https://acme.com"),
    ).startup
    assert acme_com.possible_duplicate_of is None
    redirecting_service = build_service(final_urls={"https://acme.io": "https://acme.com"})

    result = redirecting_service.ingest(
        get_source(SourceKey.MANUAL),
        build_raw_startup("acme", "Acme", website="https://acme.io"),
    )

    assert result.startup == acme_io
    acme_com.refresh_from_db()
    assert acme_com.possible_duplicate_of == acme_io


def test_platform_links_do_not_merge_different_startups():
    service = build_service()
    first = service.ingest(
        get_source(SourceKey.HACKER_NEWS),
        build_raw_startup("hn-1", "Tiny dates", website="https://github.com/someone/tiny-dates"),
    ).startup

    second = service.ingest(
        get_source(SourceKey.HACKER_NEWS),
        build_raw_startup("hn-2", "Brisa", website="https://github.com/brisa-flags/brisa"),
    ).startup

    assert first != second
    assert not StartupDomain.objects.exists()
    assert second.website == "https://github.com/brisa-flags/brisa"


def test_redirect_to_platform_is_not_used_as_alias():
    service = build_service(final_urls={"https://acme.com": "https://github.com/acme"})

    startup = service.ingest(
        get_source(SourceKey.HACKER_NEWS),
        build_raw_startup("hn-1", "Acme", website="https://acme.com"),
    ).startup

    assert list(startup.domains.values_list("domain", flat=True)) == ["acme.com"]
