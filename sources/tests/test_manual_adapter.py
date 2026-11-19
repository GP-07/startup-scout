import pytest

from sources.adapters.manual import ManualSourceAdapter
from startups.exceptions import InvalidWebsiteError


def test_manual_source_does_not_run_periodically():
    adapter = ManualSourceAdapter()

    assert ManualSourceAdapter.runs_periodically is False
    assert adapter.fetch_candidates({}).raw_startups == []


def test_builds_raw_startup_from_pasted_url():
    raw_startup = ManualSourceAdapter().build_raw_startup("https://www.Acme.com/pricing/")

    assert raw_startup.external_id == "acme.com/pricing"
    assert raw_startup.website == "https://www.Acme.com/pricing/"
    assert raw_startup.name == "Acme"


def test_uses_given_name_when_provided():
    raw_startup = ManualSourceAdapter().build_raw_startup("acme.com", name="Acme Robotics")

    assert raw_startup.name == "Acme Robotics"
    assert raw_startup.external_id == "acme.com"


def test_same_site_pasted_twice_has_same_external_id():
    adapter = ManualSourceAdapter()

    first = adapter.build_raw_startup("https://acme.com/")
    second = adapter.build_raw_startup("http://www.acme.com")

    assert first.external_id == second.external_id


def test_rejects_urls_without_registrable_domain():
    with pytest.raises(InvalidWebsiteError):
        ManualSourceAdapter().build_raw_startup("localhost:8000")
