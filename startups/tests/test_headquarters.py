from io import StringIO

import pytest
from django.core.management import call_command

from sources.constants import SourceKey
from sources.models import Source, SourceRecord
from startups.constants import LocationSource, OpeningOrigin
from startups.exceptions import UnknownCountryError
from startups.headquarters import correct_location, detect_location, reset_location
from startups.models import JobOpening, Startup, StartupDomain, WebsiteInspection

pytestmark = pytest.mark.django_db


def create_startup(domain="acme.com", **inspection_fields):
    startup = Startup.objects.create(name="Acme", website=f"https://{domain}")
    StartupDomain.objects.create(startup=startup, domain=domain, is_primary=True)
    WebsiteInspection.objects.create(startup=startup, **inspection_fields)
    return startup


def add_opening(startup, location, country="", timezone_name="", is_remote=None):
    JobOpening.objects.create(
        startup=startup,
        title="Backend Engineer",
        location=location,
        origin=OpeningOrigin.WEBSITE,
        country=country,
        timezone_name=timezone_name,
        is_remote=is_remote,
    )


def add_hiring_post(startup, comment_html):
    SourceRecord.objects.create(
        source=Source.objects.get(key=SourceKey.HACKER_NEWS_HIRING),
        startup=startup,
        external_id=f"post-{startup.pk}",
        payload={"comment_text": comment_html},
    )


def test_website_address_comes_first():
    startup = create_startup(domain="acme.de", organization_location="Valencia, ES")
    add_opening(startup, "New York, NY")

    detect_location(startup)

    startup.refresh_from_db()
    assert startup.hq_country == "ES"
    assert startup.hq_city == "Valencia"
    assert startup.hq_timezone == "Europe/Madrid"
    assert startup.location_source == LocationSource.WEBSITE_ADDRESS
    assert startup.location_evidence == "Valencia, ES"
    assert startup.location_detected_at is not None


def test_declared_headquarters_from_the_job_board_or_an_opening():
    board_headquarters = create_startup(
        headquarters_location="Santa Clara, California, United States"
    )
    opening_headquarters = create_startup(domain="beta.com")
    add_opening(opening_headquarters, "Berlin")
    add_opening(opening_headquarters, "San Leandro HQ")

    detect_location(board_headquarters)
    detect_location(opening_headquarters)

    assert board_headquarters.hq_country == "US"
    assert board_headquarters.hq_timezone == "America/Los_Angeles"
    assert board_headquarters.location_source == LocationSource.HEADQUARTERS
    assert opening_headquarters.hq_city == "San Leandro"
    assert opening_headquarters.location_source == LocationSource.HEADQUARTERS


def test_workplaces_give_the_most_frequent_country_and_its_city():
    startup = create_startup()
    add_opening(startup, "London")
    add_opening(startup, "Berlin")
    add_opening(startup, "Munich")
    add_opening(startup, "Remote", country="DE", timezone_name="Europe/Berlin")
    add_hiring_post(startup, "Acme | Berlin, Germany | ONSITE<p>We build things.")

    detect_location(startup)

    assert startup.hq_country == "DE"
    assert startup.hq_city == "Berlin"
    assert startup.hq_timezone == "Europe/Berlin"
    assert startup.location_source == LocationSource.WORKPLACES
    assert "Munich" in startup.location_evidence


def test_ambiguous_city_follows_the_other_workplaces():
    startup = create_startup()
    add_opening(startup, "San Carlos - Hybrid")
    add_opening(startup, "San Francisco, CA")
    add_opening(startup, "Seattle, WA")

    detect_location(startup)

    assert startup.hq_country == "US"


def test_country_domain_is_the_last_resort():
    startup = create_startup(domain="acme.co.uk")

    detect_location(startup)

    assert startup.hq_country == "GB"
    assert startup.hq_timezone == "Europe/London"
    assert startup.location_source == LocationSource.COUNTRY_DOMAIN
    assert startup.location_evidence == "acme.co.uk"


def test_without_evidence_the_location_is_unknown():
    startup = create_startup(domain="acme.io")
    startup.hq_country = "FR"
    startup.location_source = LocationSource.COUNTRY_DOMAIN
    startup.save()

    detect_location(startup)

    startup.refresh_from_db()
    assert startup.hq_country == ""
    assert startup.hq_timezone == ""
    assert startup.location_source == ""


def test_startup_without_inspection_is_detected_from_its_domain():
    startup = Startup.objects.create(name="Acme")
    StartupDomain.objects.create(startup=startup, domain="acme.es", is_primary=True)

    detect_location(startup)

    assert startup.hq_country == "ES"


def test_manual_location_is_never_overwritten():
    startup = create_startup(domain="acme.de")
    correct_location(startup, "AR", city="Rosario")

    detect_location(startup)

    startup.refresh_from_db()
    assert startup.hq_country == "AR"
    assert startup.hq_city == "Rosario"
    assert startup.hq_timezone == "America/Argentina/Cordoba"
    assert startup.location_source == LocationSource.MANUAL


def test_manual_location_without_a_known_city_uses_the_capital_zone():
    startup = create_startup()

    correct_location(startup, "us", city="Nowhere Town")

    assert startup.hq_country == "US"
    assert startup.hq_city == "Nowhere Town"
    assert startup.hq_timezone == "America/New_York"


def test_manual_location_needs_a_known_country():
    startup = create_startup()

    with pytest.raises(UnknownCountryError):
        correct_location(startup, "XX")


def test_reset_goes_back_to_automatic_detection():
    startup = create_startup(domain="acme.de")
    correct_location(startup, "AR")

    reset_location(startup)

    startup.refresh_from_db()
    assert startup.hq_country == "DE"
    assert startup.location_source == LocationSource.COUNTRY_DOMAIN


def test_detect_locations_command_detects_those_never_detected():
    pending = create_startup(domain="acme.de")
    detected = create_startup(domain="beta.fr")
    detect_location(detected)
    detected.hq_country = "XX"
    detected.save()
    output = StringIO()

    call_command("detect_locations", stdout=output)

    pending.refresh_from_db()
    detected.refresh_from_db()
    assert pending.hq_country == "DE"
    assert detected.hq_country == "XX"
    assert "country_domain: 1" in output.getvalue()

    call_command("detect_locations", "--all", stdout=StringIO())

    detected.refresh_from_db()
    assert detected.hq_country == "FR"


def test_a_tie_between_countries_goes_to_the_one_closest_to_madrid():
    startup = create_startup()
    for location in ("New York", "New York", "Berlin", "Berlin"):
        add_opening(startup, location)

    detect_location(startup)

    assert startup.hq_country == "DE"
    assert startup.hq_timezone == "Europe/Berlin"


def test_declared_headquarters_naming_several_places_keeps_the_closest():
    startup = create_startup(headquarters_location="San Francisco or London")

    detect_location(startup)

    assert startup.hq_country == "GB"


def test_openings_only_remote_count_as_near_without_country():
    startup = create_startup(domain="acme.io")
    add_opening(startup, "Remote")
    add_opening(startup, "", is_remote=True)

    detect_location(startup)

    assert startup.hq_country == ""
    assert startup.hq_timezone == ""
    assert startup.location_source == LocationSource.REMOTE
    assert startup.location_evidence == "Remote"


def test_openings_in_regions_keep_the_region_closest_to_madrid():
    startup = create_startup(domain="acme.io")
    add_hiring_post(startup, "Acme | Remote | EMEA, North America | Hiring<p>Hi.")

    detect_location(startup)

    assert startup.location_source == LocationSource.REMOTE
    assert startup.hq_timezone == "Europe/Paris"


def test_a_country_domain_wins_over_remote_openings():
    startup = create_startup(domain="acme.de")
    add_opening(startup, "Remote")

    detect_location(startup)

    assert startup.hq_country == "DE"


def test_website_address_with_only_a_country_code_is_that_country():
    startup = create_startup(organization_location="IN")

    detect_location(startup)

    assert startup.hq_country == "IN"
