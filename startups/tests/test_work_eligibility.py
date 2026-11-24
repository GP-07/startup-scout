import pytest

from startups.work_eligibility import only_where_i_cannot_work


@pytest.mark.parametrize(
    ("title", "location", "country_hint", "headquarters_country"),
    [
        ("Backend Engineer", "London", "", ""),
        ("Backend Engineer", "United Kingdom (Remote)", "", "US"),
        ("Backend Engineer", "Remote", "GB", ""),
        ("Backend Engineer", "Remote", "United Kingdom", ""),
        ("Backend Engineer", "Manchester or Edinburgh", "", ""),
        ("AI Product Engineer London, UK", "", "", ""),
        ("Senior Full-Stack Engineer", "", "", "GB"),
    ],
)
def test_openings_only_in_the_uk_are_out_of_reach(
    title, location, country_hint, headquarters_country
):
    assert only_where_i_cannot_work(title, location, country_hint, headquarters_country)


@pytest.mark.parametrize(
    ("title", "location", "country_hint", "headquarters_country"),
    [
        ("Backend Engineer", "London or Berlin", "", "GB"),
        ("Backend Engineer", "London, Munich, EU Remote", "", "GB"),
        ("Backend Engineer", "Madrid", "", "GB"),
        ("Backend Engineer", "Remote, Worldwide", "", "GB"),
        ("Senior Full-Stack Engineer - Product Remote (anywhere)", "", "", "GB"),
        ("Backend Engineer", "", "", "DE"),
        ("Backend Engineer", "", "", ""),
        ("Software Engineer, iOS/Mobile", "", "", ""),
    ],
)
def test_openings_with_somewhere_i_can_work_are_kept(
    title, location, country_hint, headquarters_country
):
    assert not only_where_i_cannot_work(title, location, country_hint, headquarters_country)


NO_SPONSORSHIP = "We are unable to provide visa sponsorship or support visa transfers."


@pytest.mark.parametrize(
    "description",
    [
        NO_SPONSORSHIP,
        "Visa sponsorship: Not available for this role.",
        "You must be legally entitled to work in Canada; we can't offer relocation.",
        "<p>Candidates must be authorized to work in the US.</p>",
    ],
)
def test_openings_outside_the_eu_that_sponsor_no_visa_are_out_of_reach(description):
    assert only_where_i_cannot_work("Backend Engineer", "New York, NY", description=description)


@pytest.mark.parametrize(
    ("location", "description"),
    [
        ("New York, NY", ""),
        ("New York, NY", "Visa sponsorship: we consider it on a case-by-case basis."),
        ("New York, NY", "Visa sponsorship and relocation support if you're moving here."),
        ("Amsterdam", NO_SPONSORSHIP),
        ("New York or Berlin", NO_SPONSORSHIP),
        ("Remote (EU)", NO_SPONSORSHIP),
        ("", NO_SPONSORSHIP),
    ],
)
def test_openings_that_sponsor_or_are_where_i_can_work_are_kept(location, description):
    assert not only_where_i_cannot_work("Backend Engineer", location, description=description)
