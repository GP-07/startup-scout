"""Reads places from location texts and measures their time difference from Madrid.

Pure functions over GeoNames data (geonamescache: countries, US states and cities of more
than 15,000 people, each with its time zone); no network and no database.

A location text such as "New York, San Francisco, Munich or London" or "Vienna, VA, USA" is
split into groups at separators ("or", "/", "|", parentheses...) and each group into parts at
commas. In a group, a country or a US state gives its cities context; without cities, the group
is the state or the country itself, placed in its capital's zone. Regions ("EU", "LATAM") and
time zones ("CET", "UTC+1") give a zone without a country. "Remote" alone is no place.
"""

import html as html_entities
import unicodedata
from dataclasses import dataclass
from datetime import UTC
from functools import cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import geonamescache
from bs4 import BeautifulSoup

from startups.constants import (
    CITY_ALIASES,
    CITY_ALTERNATE_NAME_MIN_LENGTH,
    COUNTRY_ALIASES,
    COUNTRY_CODE_LENGTH,
    COUNTRY_DOMAIN_ALIASES,
    GENERIC_COUNTRY_DOMAINS,
    HEADQUARTERS_WORDS,
    HIRING_POST_HEADER_END_PATTERN,
    HIRING_POST_HEADER_SEPARATOR,
    HIRING_POST_NOT_A_PLACE_MARKS,
    HIRING_POST_ROLE_WORDS,
    JOB_TITLE_WORDS,
    LOCATION_NOISE_WORDS,
    LOCATION_PART_SEPARATOR,
    LOCATION_SEPARATORS_PATTERN,
    MAX_HOURS_FROM_REFERENCE,
    NOT_A_PLACE_WORDS,
    REFERENCE_TIMEZONE,
    REGION_TIMEZONES,
    SECONDS_PER_HOUR,
    US_COUNTRY_CODE,
    US_STATE_ALIASES,
    US_STATE_CODE_LENGTH,
    UTC_OFFSET_PATTERN,
    UTC_OFFSET_TIMEZONE,
    LocationPartKind,
)
from startups.domains import DOMAIN_EXTRACTOR
from startups.hiring_signal import normalize_text


@dataclass(frozen=True)
class Place:
    """A country (ISO 3166-1 alpha-2, blank for a region) and an IANA time zone."""

    country: str
    timezone_name: str
    city: str = ""


@dataclass(frozen=True)
class GroupContext:
    """The country and US state that the parts of a group name ("Vienna, VA, USA")."""

    country: str = ""
    state: str = ""


@dataclass(frozen=True)
class Gazetteer:
    countries_by_name: dict
    capital_places: dict
    states_by_name: dict
    state_places: dict
    cities_by_name: dict
    cities_by_alternate_name: dict


def resolve_places(text, country_hint="", preferred_country=""):
    """Every place named in the text, once each: by group, its cities before its regions.

    `country_hint` is a country the source states apart from the text (a job board's field):
    it gives the cities context and is the place when the text names none. Among cities of the
    same name, `preferred_country` wins over the most populous.
    """
    hint_country = country_code(country_hint)
    text_without_offsets, offset_places = _utc_offset_places(text or "")
    places = list(offset_places)
    for group in LOCATION_SEPARATORS_PATTERN.split(text_without_offsets):
        places.extend(_group_places(group, hint_country, preferred_country))
    if not places and hint_country:
        places.append(country_place(hint_country))
    unique_places = []
    for place in places:
        if place is not None and place not in unique_places:
            unique_places.append(place)
    return unique_places


def resolve_place(text, country_hint="", preferred_country=""):
    """The first place named in the text, or None."""
    places = resolve_places(text, country_hint, preferred_country)
    return places[0] if places else None


def country_code(text):
    """The ISO code of a country name or code ("United Kingdom", "de"), or blank."""
    folded_text = _fold(text or "")
    if not folded_text:
        return ""
    gazetteer = _gazetteer()
    upper_code = folded_text.upper()
    if len(upper_code) == COUNTRY_CODE_LENGTH and upper_code in gazetteer.capital_places:
        return upper_code
    return COUNTRY_ALIASES.get(folded_text) or gazetteer.countries_by_name.get(folded_text, "")


def country_place(code):
    """The country placed in its capital's time zone, or None for an unknown code."""
    return _gazetteer().capital_places.get((code or "").upper())


def country_choices():
    """(ISO code, name) of every country, by name: for choosing one by hand."""
    countries = geonamescache.GeonamesCache().get_countries()
    return sorted(
        ((code, country["name"]) for code, country in countries.items()), key=_choice_label
    )


def country_name(code):
    """The English name of a country by its ISO code, or the code itself if unknown."""
    country = geonamescache.GeonamesCache().get_countries().get((code or "").upper())
    return country["name"] if country else code


def city_place(country, city_name):
    """The most populous city of that name in the country, or None."""
    candidates = _city_candidates(_fold(city_name), GroupContext(country=country), "")
    return candidates[0] if candidates else None


def closest_place(places, now):
    """The place with the smallest time difference from Madrid, or None."""
    measured = [
        (abs(hours), position, place)
        for position, place in enumerate(places)
        if (hours := hours_from_reference(place.timezone_name, now)) is not None
    ]
    return min(measured)[2] if measured else None


def hours_from_reference(timezone_name, now):
    """Hours from Madrid to the zone at that moment (New York: -6), or None if unknown."""
    zone = _zone_or_none(timezone_name)
    if zone is None:
        return None
    moment = now.astimezone(UTC)
    difference = (
        moment.astimezone(zone).utcoffset()
        - moment.astimezone(ZoneInfo(REFERENCE_TIMEZONE)).utcoffset()
    )
    return difference.total_seconds() / SECONDS_PER_HOUR


def is_near_reference(timezone_name, now):
    """Whether the zone is less than MAX_HOURS_FROM_REFERENCE hours from Madrid."""
    hours = hours_from_reference(timezone_name, now)
    return hours is not None and abs(hours) < MAX_HOURS_FROM_REFERENCE


def timezones_near_reference(timezone_names, now):
    """The zones, of those given, that are less than MAX_HOURS_FROM_REFERENCE from Madrid."""
    return [name for name in timezone_names if is_near_reference(name, now)]


def country_from_domain(domain):
    """The country of a country-code domain (`acme.de`, `acme.co.uk`), or blank.

    Domains that startups use with no tie to a country (`.io`, `.ai`, `.co`) give nothing.
    """
    suffix = DOMAIN_EXTRACTOR(domain or "").suffix
    last_label = suffix.rsplit(".", 1)[-1].lower()
    if len(last_label) != COUNTRY_CODE_LENGTH or last_label in GENERIC_COUNTRY_DOMAINS:
        return ""
    code = COUNTRY_DOMAIN_ALIASES.get(last_label, last_label.upper())
    return code if country_place(code) is not None else ""


def names_headquarters(text):
    """Whether a location text declares the headquarters ("San Leandro HQ")."""
    normalized_text = f" {normalize_text(text or '')} "
    return any(f" {word} " in normalized_text for word in HEADQUARTERS_WORDS)


def hiring_post_header(comment_html):
    """The header line of a "Who is hiring?" post, as text: "Acme | Engineer | Berlin"."""
    header_html = HIRING_POST_HEADER_END_PATTERN.split(comment_html or "", maxsplit=1)[0]
    header = BeautifulSoup(html_entities.unescape(header_html), "html.parser").get_text(" ")
    return " ".join(header.split())


def hiring_post_places(comment_html):
    """Places in the header line of a "Who is hiring?" post, after the company name."""
    places = []
    for segment in hiring_post_header(comment_html).split(HIRING_POST_HEADER_SEPARATOR)[1:]:
        if any(mark in segment for mark in HIRING_POST_NOT_A_PLACE_MARKS) or _names_a_role(segment):
            continue
        for place in resolve_places(segment):
            if place not in places:
                places.append(place)
    return places


def _names_a_role(segment):
    """Whether a header segment names roles ("Founding Engineer", "Product Designers")."""
    role_words = HIRING_POST_ROLE_WORDS | set(JOB_TITLE_WORDS)
    return any(
        word in role_words or word.removesuffix("s") in role_words
        for word in normalize_text(segment).split()
    )


def _utc_offset_places(text):
    places = [
        Place("", UTC_OFFSET_TIMEZONE.format(sign="-" if sign == "+" else "+", hours=int(hours)))
        for sign, hours in UTC_OFFSET_PATTERN.findall(text)
    ]
    return UTC_OFFSET_PATTERN.sub(" ", text), places


def _group_places(group, hint_country, preferred_country):
    """Places of one group: its cities in their context, else its state or country."""
    parts = [part for part in group.split(LOCATION_PART_SEPARATOR) if _fold(part)]
    context = GroupContext(country=hint_country)
    region_places = []
    city_names = []
    for position, part in enumerate(parts):
        kind, value = _classify(part, is_first=position == 0)
        if kind == LocationPartKind.REGION:
            region_places.append(Place("", value))
        elif kind == LocationPartKind.COUNTRY:
            context = GroupContext(country=value, state=context.state)
        elif kind == LocationPartKind.STATE:
            context = GroupContext(country=US_COUNTRY_CODE, state=value)
        elif kind == LocationPartKind.CITY:
            city_names.append(value)
    if city_names:
        city_places = []
        for city_name in city_names:
            candidates = _city_candidates(city_name, context, preferred_country)
            if candidates:
                city_places.append(candidates[0])
        return (city_places or [_context_place(context)]) + region_places
    if context.state or context.country:
        if context.country == hint_country and not context.state and not region_places:
            return []  # Only the hint: it is the fallback, not a place of the text.
        return [_context_place(context)] + region_places
    return region_places


def _classify(part, is_first):
    """(`LocationPartKind`, value) for a part, or (None, None).

    The first part of a group is a city before a state ("New York, New York"); the next ones
    are its context ("Vienna, VA"), or more cities ("Berlin, Munich").
    """
    for candidate in _candidate_texts(part):
        if candidate in NOT_A_PLACE_WORDS:
            return None, None
        if candidate in REGION_TIMEZONES:
            return LocationPartKind.REGION, REGION_TIMEZONES[candidate]
        # Two-letter words are countries only by alias ("UK", "US"): "DE" or "IN" are not.
        is_country_name = len(candidate) > COUNTRY_CODE_LENGTH or candidate in COUNTRY_ALIASES
        code = country_code(candidate) if is_country_name else ""
        if code:
            return LocationPartKind.COUNTRY, code
        state = _state_code(part.strip(), candidate)
        city_name = CITY_ALIASES.get(candidate, candidate)
        is_city = city_name in _gazetteer().cities_by_name
        # "Virginia" is the state, not the South African city; "Washington" is the US city.
        if is_first and is_city and (not state or _has_us_city(city_name)):
            return LocationPartKind.CITY, city_name
        if state:
            return LocationPartKind.STATE, state
        # After a city, an uppercase code that is not a US state is a country ("Valencia, ES").
        if not is_first and _is_country_code(part.strip()):
            return LocationPartKind.COUNTRY, part.strip()
        if is_city or city_name in _gazetteer().cities_by_alternate_name:
            return LocationPartKind.CITY, city_name
    return None, None


def _is_country_code(text):
    return (
        len(text) == COUNTRY_CODE_LENGTH and text.isupper() and text in _gazetteer().capital_places
    )


def _has_us_city(city_name):
    cities = _gazetteer().cities_by_name.get(city_name, [])
    return any(city["countrycode"] == US_COUNTRY_CODE for city in cities)


def _candidate_texts(part):
    """The part as written, then without words such as "Office" or "Remote"."""
    folded_part = _fold(part)
    words = folded_part.split()
    without_noise = " ".join(word for word in words if word not in LOCATION_NOISE_WORDS)
    candidates = [folded_part]
    if without_noise and without_noise != folded_part:
        candidates.append(without_noise)
    return candidates


def _state_code(original_part, folded_part):
    """A US state written by code ("VA", uppercase) or by name ("Virginia")."""
    gazetteer = _gazetteer()
    is_code = len(original_part) == US_STATE_CODE_LENGTH and original_part.isupper()
    if is_code and original_part in gazetteer.state_places:
        return original_part
    return US_STATE_ALIASES.get(folded_part) or gazetteer.states_by_name.get(folded_part, "")


def _city_candidates(city_name, context, preferred_country):
    """Places of the cities with that name, constrained by the context, best first."""
    gazetteer = _gazetteer()
    cities = gazetteer.cities_by_name.get(city_name) or gazetteer.cities_by_alternate_name.get(
        city_name, []
    )
    if context.state:
        in_state = [
            city
            for city in cities
            if city["countrycode"] == US_COUNTRY_CODE and city["admin1code"] == context.state
        ]
        # "Toronto, CA": CA is California, unless the city is in the country CA.
        cities = in_state or [city for city in cities if city["countrycode"] == context.state]
    elif context.country:
        cities = [city for city in cities if city["countrycode"] == context.country]
    preferred = [city for city in cities if city["countrycode"] == preferred_country]
    ranked = sorted(preferred or cities, key=_population, reverse=True)
    return [Place(city["countrycode"], city["timezone"], city["name"]) for city in ranked]


def _context_place(context):
    gazetteer = _gazetteer()
    if context.state:
        return gazetteer.state_places[context.state]
    return gazetteer.capital_places.get(context.country)


def _fold(text):
    """Lowercase, no accents nor dots, single spaces, no punctuation around."""
    without_accents = "".join(
        character
        for character in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(character)
    )
    words = without_accents.lower().replace(".", "").split()
    return " ".join(words).strip(" -–—_*'\"!?¡¿0123456789±+")


def _zone_or_none(timezone_name):
    if not timezone_name:
        return None
    try:
        return ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def _choice_label(choice):
    return _fold(choice[1])


def _population(city):
    return city["population"]


@cache
def _gazetteer():
    """Indexes over GeoNames data, built once per process."""
    geonames = geonamescache.GeonamesCache()
    cities = list(geonames.get_cities().values())
    cities_by_name = {}
    cities_by_alternate_name = {}
    for city in cities:
        cities_by_name.setdefault(_fold(city["name"]), []).append(city)
        for alternate_name in city["alternatenames"]:
            # Latin names only, and no airport codes ("PAR").
            if (
                alternate_name.isascii()
                and not alternate_name.isupper()
                and len(alternate_name) >= CITY_ALTERNATE_NAME_MIN_LENGTH
            ):
                cities_by_alternate_name.setdefault(_fold(alternate_name), []).append(city)
    countries = geonames.get_countries()
    capital_places = {}
    for code, country in countries.items():
        capital = _capital_city(cities, code, _fold(country["capital"] or ""))
        if capital is not None:
            capital_places[code] = Place(code, capital["timezone"])
    states = geonames.get_us_states()
    state_places = {}
    for code in states:
        state_cities = [
            city
            for city in cities
            if city["countrycode"] == US_COUNTRY_CODE and city["admin1code"] == code
        ]
        if state_cities:
            largest_city = max(state_cities, key=_population)
            state_places[code] = Place(US_COUNTRY_CODE, largest_city["timezone"])
    return Gazetteer(
        countries_by_name={_fold(country["name"]): code for code, country in countries.items()},
        capital_places=capital_places,
        states_by_name={_fold(state["name"]): code for code, state in states.items()},
        state_places=state_places,
        cities_by_name=cities_by_name,
        cities_by_alternate_name=cities_by_alternate_name,
    )


def _capital_city(cities, country, capital_name):
    """The country's capital, or its most populous city when the capital is not listed."""
    country_cities = [city for city in cities if city["countrycode"] == country]
    capitals = [city for city in country_cities if _fold(city["name"]) == capital_name]
    candidates = capitals or country_cities
    return max(candidates, key=_population) if candidates else None
