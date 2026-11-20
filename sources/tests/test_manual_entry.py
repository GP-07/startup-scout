from unittest import mock

import pytest

from sources.manual_entry import add_startup_manually
from startups.exceptions import InvalidWebsiteError
from startups.ingestion import StartupIngestionService
from startups.tests.fakes import FakeRedirectResolver

pytestmark = pytest.mark.django_db


def build_ingestion_service():
    return StartupIngestionService(redirect_resolver=FakeRedirectResolver())


def test_new_startup_is_created_and_its_website_inspection_scheduled():
    on_startup_created = mock.Mock()

    result = add_startup_manually(
        "https://www.acme.com/pricing",
        name="Acme",
        ingestion_service=build_ingestion_service(),
        on_startup_created=on_startup_created,
    )

    assert result.created is True
    assert result.startup.name == "Acme"
    assert result.startup.field_sources["name"] == "manual"
    on_startup_created.assert_called_once_with(result.startup)


def test_known_website_returns_the_existing_startup():
    service = build_ingestion_service()
    first = add_startup_manually(
        "https://acme.com", ingestion_service=service, on_startup_created=mock.Mock()
    )
    on_startup_created = mock.Mock()

    second = add_startup_manually(
        "acme.com/about", ingestion_service=service, on_startup_created=on_startup_created
    )

    assert second.created is False
    assert second.startup == first.startup
    on_startup_created.assert_not_called()


def test_invalid_website_is_rejected():
    with pytest.raises(InvalidWebsiteError):
        add_startup_manually(
            "not a url", ingestion_service=build_ingestion_service(), on_startup_created=mock.Mock()
        )
