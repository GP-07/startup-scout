from django.urls import reverse

from startups.blacklist import blacklist_domain

RULES_URL = reverse("web:rules")


def test_rules_page_shows_the_business_rules_from_their_source(logged_client):
    blacklist_domain("frameworkheroes.com", "Lista negra: bolsa de trabajo")

    response = logged_client.get(RULES_URL)

    content = response.content.decode()
    assert response.status_code == 200
    # Sources, enabled and discarded.
    assert "HN Who is hiring" in content
    assert "Startupxplore" in content
    # Openings: age and the roles discarded.
    assert "60 días" in content
    assert "founding" in content
    assert "full stack" in content
    # Languages and countries.
    assert "German" in content
    assert "United Kingdom" in content
    assert "unable" in content
    # Time zone and the blacklist.
    assert "Europe/Madrid" in content
    assert "frameworkheroes.com" in content


def test_rules_page_is_read_only(logged_client):
    content = logged_client.get(RULES_URL).content.decode()

    assert "<form" not in content.split("<main", 1)[1].split("</main>", 1)[0]
