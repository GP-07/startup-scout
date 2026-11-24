"""Decides where a startup is established, to measure its time difference from Madrid.

The evidence is already stored, so detecting needs no requests. By decreasing priority
(docs/startup-scout-design.md §3):

1. A location corrected by hand: never overwritten.
2. The schema.org address on its home page.
3. A declared headquarters: the office its job board calls so, or an opening at an "HQ".
4. Its workplaces: the most frequent country among its openings and "Who is hiring?" posts.
5. A country-code domain (`.de`, `.co.uk`), but not those used with no tie (`.io`, `.ai`).
6. Openings only "Remote" or in regions ("EMEA, North America"): no country, at the closest
   region's zone, or blank (counted as near Madrid) when they name none.

The zone is the city's when known, else the capital's. Whenever several candidates are left (a
tie between countries, several places in one text), the closest to Madrid wins.
"""

from collections import Counter
from dataclasses import dataclass

from django.utils import timezone

from sources.constants import SourceKey
from startups.constants import (
    COUNTRY_CODE_LENGTH,
    LOCATION_EVIDENCE_MAX_LENGTH,
    LOCATION_EVIDENCE_SEPARATOR,
    STARTUP_LOCATION_FIELDS,
    LocationSource,
)
from startups.exceptions import UnknownCountryError
from startups.job_listing import is_remote_text
from startups.locations import (
    Place,
    city_place,
    closest_place,
    country_code,
    country_from_domain,
    country_place,
    hiring_post_header,
    hiring_post_places,
    names_headquarters,
    resolve_places,
)
from startups.models import WebsiteInspection


@dataclass(frozen=True)
class LocationFinding:
    place: object
    source: str
    evidence: str


@dataclass(frozen=True)
class Workplace:
    """A place where the startup hires, and the text that names it.

    `places` may be empty for a remote opening that names no place.
    """

    evidence: str
    places: tuple
    is_remote: bool = False


def detect_location(startup):
    """Store where the startup is established, unless it was corrected by hand."""
    if startup.location_source == LocationSource.MANUAL:
        return startup
    finding = _find_location(startup)
    if finding is None:
        _save(startup, country="", city="", timezone_name="", source="", evidence="")
    else:
        _save(
            startup,
            country=finding.place.country,
            city=finding.place.city,
            timezone_name=finding.place.timezone_name,
            source=finding.source,
            evidence=finding.evidence,
        )
    return startup


def correct_location(startup, country, city=""):
    """Set the location by hand: the country's ISO code and, optionally, its city.

    The zone is the city's when GeoNames knows it, else the capital's. Raises
    `UnknownCountryError` for an unknown country.
    """
    code = country_code(country)
    capital = country_place(code)
    if capital is None:
        raise UnknownCountryError(country)
    city_name = " ".join((city or "").split())
    place = (city_place(code, city_name) if city_name else None) or capital
    _save(
        startup,
        country=code,
        city=place.city or city_name,
        timezone_name=place.timezone_name,
        source=LocationSource.MANUAL,
        evidence="",
    )
    return startup


def reset_location(startup):
    """Drop a correction by hand and detect the location again."""
    startup.location_source = ""
    return detect_location(startup)


def _find_location(startup):
    """The first finding by priority. Among several candidates, the closest to Madrid wins."""
    now = timezone.now()
    inspection = WebsiteInspection.objects.filter(startup=startup).first()
    workplaces = _workplaces(startup, now)
    finders = (
        _website_address(inspection, now),
        _declared_headquarters(inspection, workplaces, now),
        _most_frequent_workplace(workplaces, now),
        _country_domain(startup),
        _remote_or_regions(workplaces, now),
    )
    return next((finding for finding in finders if finding is not None), None)


def _website_address(inspection, now):
    text = inspection.organization_location if inspection else ""
    # An address with only `addressCountry` ("IN") is a country code, not a US state.
    place = country_place(text) if len(text) == COUNTRY_CODE_LENGTH else None
    place = place or _closest_country_place(resolve_places(text), now)
    return LocationFinding(place, LocationSource.WEBSITE_ADDRESS, text) if place else None


def _declared_headquarters(inspection, workplaces, now):
    texts = [inspection.headquarters_location] if inspection else []
    texts.extend(
        workplace.evidence for workplace in workplaces if names_headquarters(workplace.evidence)
    )
    for text in texts:
        place = _closest_country_place(resolve_places(text), now)
        if place is not None:
            return LocationFinding(place, LocationSource.HEADQUARTERS, text)
    return None


def _most_frequent_workplace(workplaces, now):
    """The country most of its workplaces are in, at its most frequent city or zone.

    A tie between countries goes to the one closest to Madrid ("New York" and "Berlin" twice
    each: Germany); so does a tie between cities.
    """
    place = _most_frequent_place(workplaces, now)
    if place is None:
        return None
    country = place.country
    evidence = LOCATION_EVIDENCE_SEPARATOR.join(
        dict.fromkeys(
            workplace.evidence
            for workplace in workplaces
            if country in {workplace_place.country for workplace_place in workplace.places}
        )
    )
    return LocationFinding(
        place, LocationSource.WORKPLACES, evidence[:LOCATION_EVIDENCE_MAX_LENGTH]
    )


def _most_frequent_place(workplaces, now):
    """The representative place of the most frequent country, or None without countries."""
    countries = Counter()
    for workplace in workplaces:
        countries.update({place.country for place in workplace.places if place.country})
    if not countries:
        return None
    top_count = max(countries.values())
    candidates = [
        _country_representative(workplaces, country, now)
        for country, count in countries.items()
        if count == top_count
    ]
    return closest_place(candidates, now)


def _country_representative(workplaces, country, now):
    """The most frequent city of the country among the workplaces, else its capital."""
    places = [
        place for workplace in workplaces for place in workplace.places if place.country == country
    ]
    cities = Counter(place for place in places if place.city)
    if not cities:
        return country_place(country)
    top_count = max(cities.values())
    return closest_place([city for city, count in cities.items() if count == top_count], now)


def _remote_or_regions(workplaces, now):
    """Openings only remote or in regions: no country, near Madrid unless its regions are far.

    With regions ("EMEA, North America") the zone is the closest one; only "Remote" leaves the
    zone blank, which the list counts as near (docs/startup-scout-design.md §3).
    """
    remote_workplaces = [
        workplace
        for workplace in workplaces
        if workplace.is_remote or any(not place.country for place in workplace.places)
    ]
    if not remote_workplaces:
        return None
    region_places = [
        place for workplace in remote_workplaces for place in workplace.places if not place.country
    ]
    place = closest_place(region_places, now) or Place("", "")
    evidence = LOCATION_EVIDENCE_SEPARATOR.join(
        dict.fromkeys(workplace.evidence for workplace in remote_workplaces if workplace.evidence)
    )
    return LocationFinding(place, LocationSource.REMOTE, evidence[:LOCATION_EVIDENCE_MAX_LENGTH])


def _country_domain(startup):
    domain = startup.domains.filter(is_primary=True).values_list("domain", flat=True).first()
    place = country_place(country_from_domain(domain))
    return LocationFinding(place, LocationSource.COUNTRY_DOMAIN, domain) if place else None


def _workplaces(startup, now):
    """Its openings' locations and its "Who is hiring?" headers, with the places they name.

    Cities with a name shared by several countries ("San Carlos") are read again preferring
    the country most of the other workplaces are in.
    """
    texts = list(startup.job_openings.values_list("location", "country", "is_remote"))
    hiring_posts = startup.source_records.filter(source__key=SourceKey.HACKER_NEWS_HIRING)
    post_headers = [
        str((payload or {}).get("comment_text") or "")
        for payload in hiring_posts.values_list("payload", flat=True)
    ]
    first_reading = _read_workplaces(texts, post_headers, preferred_country="")
    preferred_place = _most_frequent_place(first_reading, now)
    if preferred_place is None:
        return first_reading
    return _read_workplaces(texts, post_headers, preferred_country=preferred_place.country)


def _read_workplaces(opening_texts, post_headers, preferred_country):
    workplaces = []
    for location, country, is_remote in opening_texts:
        places = resolve_places(location, preferred_country=preferred_country)
        if not places and country:
            # The location says nothing ("Remote"), but the job board gave its country.
            places = [country_place(country)]
        remote = bool(is_remote or is_remote_text(location))
        if places or remote:
            workplaces.append(Workplace(location or country, tuple(places), is_remote=remote))
    for comment_html in post_headers:
        header = hiring_post_header(comment_html)
        places = hiring_post_places(comment_html)
        remote = bool(is_remote_text(header))
        if places or remote:
            workplaces.append(Workplace(header, tuple(places), is_remote=remote))
    return workplaces


def _closest_country_place(places, now):
    return closest_place([place for place in places if place.country], now)


def _save(startup, country, city, timezone_name, source, evidence):
    startup.hq_country = country
    startup.hq_city = city
    startup.hq_timezone = timezone_name
    startup.location_source = source
    startup.location_evidence = evidence[:LOCATION_EVIDENCE_MAX_LENGTH]
    startup.location_detected_at = timezone.now()
    startup.save(update_fields=STARTUP_LOCATION_FIELDS)
