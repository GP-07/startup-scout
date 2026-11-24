"""Finds languages other than English and Spanish that an opening requires.

Pure functions: no network and no database. A language named in the title is required
("Developer Advocate (German)"). In the description, it is required when its sentence also
says how ("Fluent in German", "C1 French", "Deutschkenntnisse") and does not make it optional
("German is a plus").
"""

import html as html_entities

from bs4 import BeautifulSoup

from startups.constants import (
    DESCRIPTION_BLOCK_TAGS,
    DESCRIPTION_SENTENCE_SEPARATORS,
    LANGUAGE_REQUIREMENT_COMPOUNDS,
    LANGUAGE_REQUIREMENT_WORDS,
    MULTILINGUAL_LANGUAGE,
    MULTILINGUAL_WORDS,
    OPTIONAL_LANGUAGE_WORDS,
    OTHER_LANGUAGES,
)
from startups.hiring_signal import normalize_text
from startups.job_titles import contains_any


def required_other_languages(title, description):
    """Names of the other languages required, in a fixed order ("German", "French")."""
    required = set(_languages_in(_padded(title)))
    if contains_any(_padded(title), MULTILINGUAL_WORDS):
        required.add(MULTILINGUAL_LANGUAGE)
    for sentence in description_sentences(description):
        required.update(_required_in_sentence(_padded(sentence)))
    order = [name for name, _ in OTHER_LANGUAGES] + [MULTILINGUAL_LANGUAGE]
    return [name for name in order if name in required]


def _required_in_sentence(sentence):
    if contains_any(sentence, OPTIONAL_LANGUAGE_WORDS):
        return []
    required = [
        language
        for compound, language in LANGUAGE_REQUIREMENT_COMPOUNDS.items()
        if contains_any(sentence, (compound,))
    ]
    if contains_any(sentence, LANGUAGE_REQUIREMENT_WORDS):
        required.extend(_languages_in(sentence))
    return required


def _languages_in(padded_text):
    return [name for name, words in OTHER_LANGUAGES if contains_any(padded_text, words)]


def description_sentences(description):
    """The sentences and list items of a description, as plain text."""
    return DESCRIPTION_SENTENCE_SEPARATORS.split(plain_text(description))


def plain_text(description):
    """The description as text with line breaks, from plain text or (escaped) HTML."""
    unescaped = html_entities.unescape(description or "")
    if "<" not in unescaped:
        return unescaped
    soup = BeautifulSoup(unescaped, "html.parser")
    for block in soup.find_all(DESCRIPTION_BLOCK_TAGS):
        block.insert_after("\n")
    return soup.get_text(" ")


def _padded(text):
    return f" {normalize_text(text or '')} "
