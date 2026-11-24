import json

import pytest

from startups.organization_address import organization_location


def json_ld_page(data):
    return (
        f"<html><head><script type='application/ld+json'>{json.dumps(data)}</script></head></html>"
    )


def test_postal_address_of_the_organization():
    page = json_ld_page(
        {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": "Acme",
            "address": {
                "@type": "PostalAddress",
                "streetAddress": "Calle Falsa 123",
                "addressLocality": "Valencia",
                "addressCountry": "ES",
            },
        }
    )

    assert organization_location(page) == "Valencia, ES"


def test_organization_inside_a_graph_with_a_country_object():
    page = json_ld_page(
        {
            "@graph": [
                {"@type": "WebSite", "name": "Acme"},
                {
                    "@type": ["Organization", "Corporation"],
                    "address": [
                        {
                            "addressLocality": "Austin",
                            "addressRegion": "TX",
                            "addressCountry": {"@type": "Country", "name": "US"},
                        }
                    ],
                },
            ]
        }
    )

    assert organization_location(page) == "Austin, TX, US"


def test_address_written_as_text():
    page = json_ld_page({"@type": "Organization", "address": "Lyon, France"})

    assert organization_location(page) == "Lyon, France"


@pytest.mark.parametrize(
    "page",
    [
        "<html><body>No data</body></html>",
        json_ld_page({"@type": "Person", "address": {"addressLocality": "Oslo"}}),
        "<script type='application/ld+json'>{broken</script>",
    ],
)
def test_no_organization_address(page):
    assert organization_location(page) == ""
