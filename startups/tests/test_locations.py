from datetime import UTC, datetime

import pytest

from startups.locations import (
    Place,
    closest_place,
    country_code,
    country_from_domain,
    country_place,
    hiring_post_places,
    hours_from_reference,
    names_headquarters,
    resolve_place,
    resolve_places,
    timezones_near_reference,
)

SUMMER = datetime(2026, 7, 15, 12, tzinfo=UTC)
WINTER = datetime(2026, 1, 15, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Berlin", Place("DE", "Europe/Berlin", "Berlin")),
        ("Munich", Place("DE", "Europe/Berlin", "Munich")),
        ("Zurich, Switzerland", Place("CH", "Europe/Zurich", "Zürich")),
        ("New York, New York", Place("US", "America/New_York", "New York City")),
        ("NYC (HYBRID)", Place("US", "America/New_York", "New York City")),
        ("San Francisco Office", Place("US", "America/Los_Angeles", "San Francisco")),
        ("Idaho Falls, ID", Place("US", "America/Boise", "Idaho Falls")),
        ("Mexico City, Mexico", Place("MX", "America/Mexico_City", "Mexico City")),
        ("Sao Paulo", Place("BR", "America/Sao_Paulo", "São Paulo")),
        ("Cologne", Place("DE", "Europe/Berlin", "Köln")),
    ],
)
def test_cities_resolve_to_their_country_and_zone(text, expected):
    assert resolve_place(text) == expected


def test_a_state_gives_the_city_its_context():
    assert resolve_place("Vienna, VA, USA").country == "US"
    assert resolve_place("Vienna").country == "AT"
    assert resolve_place("Paris, TX").timezone_name == "America/Chicago"


def test_a_state_alone_gives_its_zone():
    assert resolve_place("California (Remote)") == Place("US", "America/Los_Angeles", "")


@pytest.mark.parametrize(
    ("text", "country"),
    [
        ("United States", "US"),
        ("Remote - U.S.A.", "US"),
        ("REMOTE (US)", "US"),
        ("ONSITE (UK)", "GB"),
        ("England", "GB"),
        ("Germany (Remote)", "DE"),
        ("UNITED STATES", "US"),
    ],
)
def test_countries_resolve_to_their_capital_zone(text, country):
    assert resolve_place(text).country == country


def test_country_zone_is_its_capital_zone():
    assert country_place("CA") == Place("CA", "America/Toronto", "")
    assert country_place("ES") == Place("ES", "Europe/Madrid", "")


@pytest.mark.parametrize(
    ("text", "timezone_name"),
    [
        ("Remote (EU)", "Europe/Paris"),
        ("EMEA", "Europe/Paris"),
        ("London, Munich, EU Remote", "Europe/London"),
        ("LATAM", "America/Sao_Paulo"),
        ("Berlin, Germany (or remote, CET overlap)", "Europe/Berlin"),
        ("+/-1 Central European Time", "Europe/Paris"),
        ("UTC+3", "Etc/GMT-3"),
        ("REMOTE (anywhere, EST hours)", "America/New_York"),
    ],
)
def test_regions_and_time_zones_give_a_zone(text, timezone_name):
    assert resolve_place(text).timezone_name == timezone_name


def test_a_region_has_no_country():
    assert resolve_place("Europe").country == ""


@pytest.mark.parametrize("text", ["Remote", "Remote, Worldwide", "Field", "", "Full-time"])
def test_texts_without_a_place_give_nothing(text):
    assert resolve_places(text) == []


def test_several_places_in_one_text():
    places = resolve_places("New York, San Francisco, Munich or London")

    assert [place.country for place in places] == ["US", "US", "DE", "GB"]


def test_ambiguous_city_prefers_the_most_populous_or_the_preferred_country():
    assert resolve_place("San Carlos - Hybrid").country == "VE"
    assert resolve_place("San Carlos - Hybrid", preferred_country="US").country == "US"


def test_country_hint_resolves_a_text_without_place_and_constrains_cities():
    assert resolve_place("Remote", country_hint="US") == Place("US", "America/New_York", "")
    assert resolve_place("Paris", country_hint="United States").country == "US"


def test_country_code_reads_names_and_codes():
    assert country_code("United Kingdom") == "GB"
    assert country_code("de") == "DE"
    assert country_code("Narnia") == ""


def test_closest_place_to_madrid():
    places = [Place("US", "America/New_York", ""), Place("GB", "Europe/London", "")]

    assert closest_place(places, SUMMER).country == "GB"
    assert closest_place([], SUMMER) is None


def test_hours_from_madrid_follow_daylight_saving_time():
    assert hours_from_reference("Europe/Madrid", SUMMER) == 0
    assert hours_from_reference("America/New_York", WINTER) == -6
    assert hours_from_reference("Asia/Kolkata", WINTER) == 4.5
    assert hours_from_reference("America/Sao_Paulo", WINTER) == -4
    assert hours_from_reference("America/Sao_Paulo", SUMMER) == -5


def test_zones_near_madrid_are_less_than_five_hours_away():
    zones = ["Europe/London", "America/Sao_Paulo", "America/New_York", "Asia/Dubai", "Bad/Zone"]

    assert timezones_near_reference(zones, WINTER) == [
        "Europe/London",
        "America/Sao_Paulo",
        "Asia/Dubai",
    ]
    assert timezones_near_reference(zones, SUMMER) == ["Europe/London", "Asia/Dubai"]


@pytest.mark.parametrize(
    ("domain", "country"),
    [
        ("acme.de", "DE"),
        ("acme.co.uk", "GB"),
        ("acme.com.br", "BR"),
        ("acme.io", ""),
        ("acme.co", ""),
        ("acme.ai", ""),
        ("acme.com", ""),
    ],
)
def test_country_domain(domain, country):
    assert country_from_domain(domain) == country


def test_names_headquarters():
    assert names_headquarters("San Leandro HQ")
    assert names_headquarters("Headquarters")
    assert not names_headquarters("San Francisco Office")


def test_hiring_post_places_read_the_header_without_the_company_name():
    comment = (
        "Berlin Labs | Founding Engineer | London, United Kingdom | ONSITE | Full-time"
        "<p>We are based in Paris too.</p>"
    )

    assert [place.country for place in hiring_post_places(comment)] == ["GB"]


def test_a_state_name_wins_over_a_foreign_city_of_the_same_name():
    assert resolve_place("Virginia") == Place("US", "America/New_York", "")
    assert resolve_place("Washington").city == "Washington"


def test_hiring_post_places_skip_segments_that_name_roles():
    comment = (
        "Acme | Software Engineers (backend, mobile) | COO — founder-level role"
        " | Remote (US/EU timezones preferred) | Full-time"
    )

    assert hiring_post_places(comment) == [
        Place("US", "America/New_York", ""),
        Place("", "Europe/Paris", ""),
    ]


def test_country_code_after_a_city():
    assert resolve_place("Valencia, ES").country == "ES"
    assert resolve_place("Berlin, DE").country == "DE"
    assert resolve_place("Toronto, CA").country == "CA"
    assert resolve_place("San Jose, CA").country == "US"
