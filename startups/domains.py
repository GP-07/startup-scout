import unicodedata
from urllib.parse import urlsplit

import tldextract

from startups.constants import (
    DEFAULT_URL_SCHEME,
    LEGAL_NAME_SUFFIXES,
    NON_ALPHANUMERIC_PATTERN,
    URL_SCHEME_PATTERN,
)
from startups.exceptions import InvalidWebsiteError

# Bundled Public Suffix List snapshot, private suffixes included (vercel.app, github.io...),
# so `foo.vercel.app` and `bar.vercel.app` stay different domains. No network access, no cache.
DOMAIN_EXTRACTOR = tldextract.TLDExtract(
    include_psl_private_domains=True,
    suffix_list_urls=(),
    cache_dir=None,
)


def normalize_domain(website):
    """Registrable domain of a URL or host: `https://app.acme.com/x` -> `acme.com`."""
    hostname = _extract_hostname(website)
    try:
        ascii_hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError as error:
        raise InvalidWebsiteError(website) from error

    extracted = DOMAIN_EXTRACTOR(ascii_hostname)
    if not extracted.domain or not extracted.suffix:
        raise InvalidWebsiteError(website)
    return f"{extracted.domain}.{extracted.suffix}"


def normalize_name(name):
    """Comparable form of a company name: no accents, punctuation, case or legal suffix."""
    without_accents = "".join(
        character
        for character in unicodedata.normalize("NFKD", name)
        if not unicodedata.combining(character)
    )
    without_dots = without_accents.lower().replace(".", "")
    tokens = NON_ALPHANUMERIC_PATTERN.sub(" ", without_dots).split()
    while len(tokens) > 1 and tokens[-1] in LEGAL_NAME_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def _extract_hostname(website):
    value = (website or "").strip()
    if not value or " " in value:
        raise InvalidWebsiteError(website)
    if not URL_SCHEME_PATTERN.match(value):
        value = f"{DEFAULT_URL_SCHEME}{value}"
    hostname = urlsplit(value).hostname
    if not hostname:
        raise InvalidWebsiteError(website)
    return hostname.rstrip(".").lower()
