import pytest

from startups.domains import is_identifying_domain, normalize_domain, normalize_name
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


@pytest.mark.parametrize(
    ("website", "expected_domain"),
    [
        ("https://acme.substack.com/p/launch", "acme.substack.com"),
        ("https://www.acme.itch.io", "acme.itch.io"),
        ("https://acme.medium.com", "acme.medium.com"),
        ("https://medium.com/@acme/launch", "medium.com"),
        ("https://acme-app.bolt.host", "acme-app.bolt.host"),
    ],
)
def test_sites_hosted_as_subdomains_of_shared_hosts_keep_their_subdomain(website, expected_domain):
    assert normalize_domain(website) == expected_domain


@pytest.mark.parametrize(
    "website",
    [
        "https://github.com/acme/acme",
        "https://apps.apple.com/app/acme/id123",
        "https://play.google.com/store/apps/details?id=com.acme",
        "https://www.youtube.com/watch?v=abc",
        "https://medium.com/@acme/launch",
        "https://x.com/acme",
        "https://plugins.jetbrains.com/plugin/123-acme",
        "https://marketplace.visualstudio.com/items?itemName=acme.acme",
        "https://vercel.com/templates/next.js/acme",
        "https://jobs.ashbyhq.com/acme",
        "https://grnh.se/abc123",
        "https://acme.wd1.myworkdayjobs.com/External",
        "https://acme.typeform.com/to/apply",
        "https://techcrunch.com/2026/11/02/acme-raises",
    ],
)
def test_platform_domains_do_not_identify_a_startup(website):
    assert is_identifying_domain(normalize_domain(website)) is False


@pytest.mark.parametrize(
    "website",
    ["https://acme.com", "https://acme.vercel.app", "https://acme.substack.com"],
)
def test_own_domains_identify_a_startup(website):
    assert is_identifying_domain(normalize_domain(website)) is True
