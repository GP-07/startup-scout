import unicodedata
from urllib.parse import urlsplit

import tldextract

from startups.constants import (
    DEFAULT_URL_SCHEME,
    LEGAL_NAME_SUFFIXES,
    NON_ALPHANUMERIC_PATTERN,
    NON_IDENTIFYING_DOMAINS,
    SHARED_HOST_DOMAINS,
    URL_SCHEME_PATTERN,
    WWW_SUBDOMAIN,
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
    """Registrable domain of a URL or host: `https://app.acme.com/x` -> `acme.com`.

    Sites hosted as subdomains of a shared host keep their subdomain: `acme.substack.com`.
    """
    hostname = _extract_hostname(website)
    try:
        ascii_hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError as error:
        raise InvalidWebsiteError(website) from error

    extracted = DOMAIN_EXTRACTOR(ascii_hostname)
    if not extracted.domain or not extracted.suffix:
        raise InvalidWebsiteError(website)
    registrable_domain = f"{extracted.domain}.{extracted.suffix}"
    if registrable_domain in SHARED_HOST_DOMAINS:
        site_label = _last_non_www_label(extracted.subdomain)
        if site_label:
            return f"{site_label}.{registrable_domain}"
    return registrable_domain


def is_identifying_domain(domain):
    """Whether a normalized domain identifies one startup (and not a platform like GitHub)."""
    return domain not in NON_IDENTIFYING_DOMAINS and domain not in SHARED_HOST_DOMAINS


def normalize_url(website):
    """Comparable form of a URL: host without `www.` plus path, e.g. `acme.com/pricing`."""
    hostname = _extract_hostname(website)
    if hostname.startswith(f"{WWW_SUBDOMAIN}."):
        hostname = hostname[len(WWW_SUBDOMAIN) + 1 :]
    path = urlsplit(_with_scheme(website.strip())).path.rstrip("/").lower()
    return f"{hostname}{path}"


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


def _last_non_www_label(subdomain):
    labels = [label for label in subdomain.split(".") if label and label != WWW_SUBDOMAIN]
    return labels[-1] if labels else ""


def _extract_hostname(website):
    value = (website or "").strip()
    if not value or " " in value:
        raise InvalidWebsiteError(website)
    hostname = urlsplit(_with_scheme(value)).hostname
    if not hostname:
        raise InvalidWebsiteError(website)
    return hostname.rstrip(".").lower()


def _with_scheme(value):
    return value if URL_SCHEME_PATTERN.match(value) else f"{DEFAULT_URL_SCHEME}{value}"
