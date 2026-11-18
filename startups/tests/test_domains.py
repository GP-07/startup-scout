import pytest

from startups.domains import normalize_domain, normalize_name
from startups.exceptions import InvalidWebsiteError


@pytest.mark.parametrize(
    ("website", "expected_domain"),
    [
        ("https://www.Example.com/pricing?ref=hn", "example.com"),
        ("example.com", "example.com"),
        ("http://example.com.", "example.com"),
        ("https://app.example.com/login", "example.com"),
        ("https://www.example.co.uk", "example.co.uk"),
        ("https://shop.example.co.uk/", "example.co.uk"),
        ("https://foo.vercel.app", "foo.vercel.app"),
        ("https://bar.github.io/project", "bar.github.io"),
        ("https://www.müller.de", "xn--mller-kva.de"),
        ("  https://Example.com  ", "example.com"),
    ],
)
def test_normalize_domain_returns_registrable_domain(website, expected_domain):
    assert normalize_domain(website) == expected_domain


def test_normalize_domain_keeps_paas_subdomains_apart():
    assert normalize_domain("https://foo.vercel.app") != normalize_domain("https://bar.vercel.app")


@pytest.mark.parametrize(
    "website",
    ["", "   ", "localhost", "http://192.168.0.1", "https://", "not a url"],
)
def test_normalize_domain_rejects_values_without_registrable_domain(website):
    with pytest.raises(InvalidWebsiteError):
        normalize_domain(website)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Acme, S.L.", "acme"),
        ("Ácme Inc.", "acme"),
        ("ACME   Labs  GmbH", "acme labs"),
        ("Acme S.L.U.", "acme"),
        ("Inc", "inc"),
        ("Café-Bar Tech", "cafe bar tech"),
    ],
)
def test_normalize_name_ignores_case_accents_punctuation_and_legal_suffixes(name, expected):
    assert normalize_name(name) == expected
