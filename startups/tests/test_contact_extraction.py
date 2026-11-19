import json

import pytest

from startups.constants import ContactRole
from startups.contact_extraction import (
    ContactCandidate,
    contact_page_links,
    extract_contacts,
    role_from_title,
)

PAGE_URL = "https://www.acme.com/about"


def page(body, head=""):
    return f"<html><head><title>Acme</title>{head}</head><body>{body}</body></html>"


def json_ld(data):
    return f'<script type="application/ld+json">{json.dumps(data)}</script>'


def by_email(candidates):
    return {candidate.email: candidate for candidate in candidates if candidate.email}


def by_name(candidates):
    return {candidate.full_name: candidate for candidate in candidates if candidate.full_name}


def test_generic_mailto_of_the_site_is_a_general_contact():
    html = page('<footer><a href="mailto:hello@acme.com?subject=Hi">Say hello</a></footer>')

    candidates = extract_contacts(html, PAGE_URL)

    assert candidates == [
        ContactCandidate(
            full_name="",
            role=ContactRole.GENERAL,
            email="hello@acme.com",
            profile_url="",
            evidence_url=PAGE_URL,
        )
    ]


def test_personal_mailto_keeps_the_name_of_the_link():
    html = page('<p>Write to <a href="mailto:jane@acme.com">Jane Roe</a></p>')

    jane = by_email(extract_contacts(html, PAGE_URL))["jane@acme.com"]

    assert jane.full_name == "Jane Roe"
    assert jane.role == ContactRole.OTHER


def test_plain_text_email_of_the_site_is_found():
    html = page("<p>Questions? founders@acme.com</p>")

    assert "founders@acme.com" in by_email(extract_contacts(html, PAGE_URL))


@pytest.mark.parametrize(
    "email",
    ["someone@gmail.com", "privacy@vendor-fictional.com", "jobs@acme.com", "careers@acme.com"],
)
def test_emails_of_other_domains_and_hiring_mailboxes_are_ignored(email):
    html = page(f'<a href="mailto:{email}">{email}</a>')

    assert extract_contacts(html, PAGE_URL) == []


def test_team_card_gives_name_role_and_linkedin_profile():
    html = page(
        '<section class="team">'
        '<div class="card"><h3>Jane Roe</h3><p>CEO &amp; Co-founder</p>'
        '<a href="https://www.linkedin.com/in/jane-roe-fictional/">LinkedIn</a></div>'
        '<div class="card"><h3>John Doe</h3><p>Co-founder, CTO</p></div>'
        '<div class="card"><h3>Ana Pérez</h3><p>Head of Design</p></div>'
        "</section>"
    )

    people = by_name(extract_contacts(html, PAGE_URL))

    assert people["Jane Roe"].role == ContactRole.CEO
    assert people["Jane Roe"].profile_url == "https://www.linkedin.com/in/jane-roe-fictional/"
    assert people["John Doe"].role == ContactRole.CTO
    assert people["John Doe"].profile_url == ""
    assert "Ana Pérez" not in people


def test_name_and_role_in_the_same_line_are_split():
    html = page("<p>Built by Jane Roe, Founder</p><p>Marta Gómez — Cofundadora y CTO</p>")

    people = by_name(extract_contacts(html, PAGE_URL))

    assert people["Jane Roe"].role == ContactRole.FOUNDER
    assert people["Marta Gómez"].role == ContactRole.CTO


def test_role_words_without_a_person_name_are_ignored():
    html = page("<h2>Our Founders</h2><p>Built for CTOs and founders who ship fast</p>")

    assert extract_contacts(html, PAGE_URL) == []


def test_json_ld_founders_and_employees_with_titles():
    organization = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": "Acme",
        "founder": [
            {
                "@type": "Person",
                "name": "Jane Roe",
                "sameAs": ["https://x.com/janeroe", "https://www.linkedin.com/in/janeroe"],
            }
        ],
        "employee": {"@type": "Person", "name": "John Doe", "jobTitle": "Chief Technology Officer"},
    }
    html = page("<p>Acme</p>", head=json_ld(organization))

    people = by_name(extract_contacts(html, PAGE_URL))

    assert people["Jane Roe"].role == ContactRole.FOUNDER
    assert people["Jane Roe"].profile_url == "https://www.linkedin.com/in/janeroe"
    assert people["John Doe"].role == ContactRole.CTO


def test_broken_json_ld_is_ignored():
    html = page("<p>Acme</p>", head='<script type="application/ld+json">{not json</script>')

    assert extract_contacts(html, PAGE_URL) == []


def test_lone_linkedin_profile_without_role_is_kept_as_other():
    html = page('<a href="https://linkedin.com/in/someone-fictional">Find me on LinkedIn</a>')

    [candidate] = extract_contacts(html, PAGE_URL)

    assert candidate.role == ContactRole.OTHER
    assert candidate.profile_url == "https://linkedin.com/in/someone-fictional"


def test_linkedin_company_pages_are_not_contacts():
    html = page('<a href="https://www.linkedin.com/company/acme">LinkedIn</a>')

    assert extract_contacts(html, PAGE_URL) == []


def test_same_person_found_twice_is_merged():
    html = page(
        "<div><h3>Jane Roe</h3><p>Founder</p></div>",
        head=json_ld(
            {
                "@type": "Person",
                "name": "Jane Roe",
                "jobTitle": "Founder & CEO",
                "email": "mailto:jane@acme.com",
            }
        ),
    )

    [jane] = extract_contacts(html, PAGE_URL)

    assert jane.role == ContactRole.CEO
    assert jane.email == "jane@acme.com"


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("CEO & Co-founder", ContactRole.CEO),
        ("Chief Executive Officer", ContactRole.CEO),
        ("Co-founder, CTO", ContactRole.CTO),
        ("Chief Technology Officer", ContactRole.CTO),
        ("Cofundadora", ContactRole.FOUNDER),
        ("Founder", ContactRole.FOUNDER),
        ("Head of Design", None),
        ("", None),
    ],
)
def test_role_from_title(title, expected):
    assert role_from_title(title) == expected


def test_contact_page_links_are_same_site_about_team_and_contact_pages():
    html = page(
        '<nav><a href="/company/about-us">About</a><a href="/team/">Team</a>'
        '<a href="/pricing">Pricing</a><a href="https://other-fictional.com/contact">x</a>'
        '<a href="/contacto">Contacto</a><a href="/team/">Team again</a></nav>'
    )

    links = contact_page_links(html, "https://www.acme.com/")

    assert links == [
        "https://www.acme.com/company/about-us",
        "https://www.acme.com/team/",
        "https://www.acme.com/contacto",
    ]


def test_customer_testimonials_naming_another_company_are_not_the_team():
    html = page(
        "<blockquote>Acme saved us weeks.</blockquote>"
        "<div><h4>Olivia Quote</h4><p>CEO at Globex</p></div>"
        "<p>Mark Sample, CTO of Initech</p>"
        "<div><h4>Paula Cliente</h4><p>Founder, Hooli</p></div>"
    )

    assert extract_contacts(html, PAGE_URL) == []


def test_job_title_naming_the_startup_itself_is_kept():
    html = page("<div><h4>Jane Roe</h4><p>CEO at Acme</p></div><p>John Doe, CTO of Acme Inc</p>")

    people = by_name(extract_contacts(html, PAGE_URL))

    assert people["Jane Roe"].role == ContactRole.CEO
    assert people["John Doe"].role == ContactRole.CTO


def test_json_ld_people_outside_the_team_are_not_contacts():
    reviews = {
        "@type": "Product",
        "name": "Acme",
        "review": [
            {
                "@type": "Review",
                "author": {"@type": "Person", "name": "Olivia Quote", "jobTitle": "CTO, Globex"},
            }
        ],
    }
    employee_elsewhere = {
        "@type": "Organization",
        "employee": {"@type": "Person", "name": "Mark Sample", "jobTitle": "CEO at Initech"},
    }
    html = page("<p>Acme</p>", head=json_ld(reviews) + json_ld(employee_elsewhere))

    assert extract_contacts(html, PAGE_URL) == []


def test_people_in_investor_and_customer_sections_are_not_the_team():
    html = page(
        "<h2>Our team</h2><div><h3>Jane Roe</h3><p>CEO</p></div>"
        "<h2>Backed by</h2><div><h3>Ivan Investor</h3><p>Founder &amp; CEO</p><p>Globex</p></div>"
        "<h2>What our customers say</h2><div><h3>Carla Client</h3><p>CTO</p></div>"
    )

    assert set(by_name(extract_contacts(html, PAGE_URL))) == {"Jane Roe"}


def test_company_in_the_fragment_after_at_is_checked():
    html = page(
        "<div><h4>Olivia Quote</h4><p>Co-founder</p><span>at</span><span>Globex</span></div>"
    )

    assert extract_contacts(html, PAGE_URL) == []


@pytest.mark.parametrize(
    "not_a_name", ["General Counsel", "San Francisco", "New York", "Customer Quotes", "ML Engineer"]
)
def test_titles_places_and_labels_next_to_a_role_are_not_names(not_a_name):
    html = page(f"<div><p>{not_a_name}</p><p>CEO</p></div>")

    assert extract_contacts(html, PAGE_URL) == []
