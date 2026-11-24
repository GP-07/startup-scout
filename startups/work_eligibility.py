"""Tells whether an opening is only in countries where I cannot work.

I am an Italian citizen living in Spain: I work without a visa in the EU, the EEA and
Switzerland. Elsewhere I need one: an opening only in the UK is always out of reach; one only
in other countries is out of reach when its description says it sponsors no visa ("We are
unable to provide visa sponsorship", "Must be authorized to work in the US").

Pure functions: no network and no database. Where an opening is, in order: the places its
location names (or the country its job board states); if none, a country its title names
("AI Product Engineer London, UK"); if none, its company's country, unless it says it is open
from anywhere. An opening that also names a place where I can work, or a region ("EU Remote"),
is kept.
"""

from startups.constants import (
    ANYWHERE_WORDS,
    COUNTRIES_REQUIRING_WORK_AUTHORIZATION,
    COUNTRIES_WITHOUT_WORK_AUTHORIZATION,
    SPONSORSHIP_REFUSAL_WORDS,
    SPONSORSHIP_WORDS,
    WORK_AUTHORIZATION_REQUIREMENTS,
)
from startups.hiring_signal import normalize_text
from startups.job_languages import description_sentences
from startups.job_titles import contains_any
from startups.locations import country_code, country_place, resolve_places


def only_where_i_cannot_work(
    title, location, country_hint="", headquarters_country="", description=""
):
    """Whether every place of the opening needs a work authorization I cannot get.

    A region ("EU Remote") or an unknown place keeps it.
    """
    countries = _opening_countries(title, location, country_hint, headquarters_country)
    if not countries or "" in countries:
        return False
    if countries <= COUNTRIES_REQUIRING_WORK_AUTHORIZATION:
        return True
    return not (countries & COUNTRIES_WITHOUT_WORK_AUTHORIZATION) and refuses_sponsorship(
        description
    )


def refuses_sponsorship(description):
    """Whether the description says the company sponsors no visa or needs work authorization."""
    for sentence in description_sentences(description):
        padded_sentence = f" {normalize_text(sentence)} "
        if contains_any(padded_sentence, WORK_AUTHORIZATION_REQUIREMENTS):
            return True
        if contains_any(padded_sentence, SPONSORSHIP_WORDS) and contains_any(
            padded_sentence, SPONSORSHIP_REFUSAL_WORDS
        ):
            return True
    return False


def _opening_countries(title, location, country_hint, headquarters_country):
    """Countries of the opening; a region counts as blank, a place where I may work."""
    places = resolve_places(location)
    if not places and country_hint:
        # A code ("GB") or a name ("United Kingdom").
        places = [place for place in [country_place(country_code(country_hint))] if place]
    if not places:
        # Titles only by country or state: their words often match small towns ("Mobile").
        places = [place for place in resolve_places(title) if not place.city]
    if places:
        return {place.country for place in places}
    padded_text = f" {normalize_text(f'{title} {location}')} "
    if headquarters_country and not contains_any(padded_text, ANYWHERE_WORDS):
        return {headquarters_country}
    return set()
