import pytest

from startups.job_languages import required_other_languages


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Developer Advocate (German)", ["German"]),
        ("Complaints Project Manager - Fluent German", ["German"]),
        (
            "Customer Care Specialist (French, German, Italian, Spanish or Polish)",
            ["French", "German", "Italian", "Polish"],
        ),
        ("Head of Customer Experience (Multilingual)", ["Multilingual"]),
        ("Senior Backend Engineer", []),
        ("Desarrollador Backend (Spanish/English)", []),
    ],
)
def test_a_language_in_the_title_is_required(title, expected):
    assert required_other_languages(title, "") == expected


@pytest.mark.parametrize(
    "description",
    [
        "Requirements:\n- 5+ years with Python\n- Fluent in German and English",
        "You speak Dutch at a professional level.",
        "Native or C1 French is required.",
        "Sehr gute Deutschkenntnisse in Wort und Schrift.",
        "<ul><li>Proficiency in Japanese (JLPT N1)</li></ul>",
    ],
)
def test_a_language_required_in_the_description(description):
    assert required_other_languages("Backend Engineer", description) != []


@pytest.mark.parametrize(
    "description",
    [
        "Fluent English is required. Spanish is a plus.",
        "Speaking German is a plus.",
        "French would be nice to have.",
        "We serve customers in Germany, France and Italy.",
        "Our German office is in Berlin.",
        "Experience with cloud-native systems; our clients are Dutch banks.",
        "",
    ],
)
def test_no_other_language_required(description):
    assert required_other_languages("Backend Engineer", description) == []


def test_html_entities_of_greenhouse_content_are_read():
    description = "&lt;p&gt;Fluent &lt;strong&gt;German&lt;/strong&gt; required.&lt;/p&gt;"

    assert required_other_languages("Backend Engineer", description) == ["German"]
