from startups.constants import HiringSignalKind
from startups.hiring_signal import detect_hiring_signal, visible_text

PAGE_URL = "https://www.acme.com/"


def page(body):
    return f"<html><head><title>Acme</title></head><body>{body}</body></html>"


def test_footer_link_to_careers_path_is_a_signal():
    html = page('<main>Robots for warehouses</main><footer><a href="/careers">Careers</a></footer>')

    signal = detect_hiring_signal(html, PAGE_URL)

    assert signal.kind == HiringSignalKind.LINK_PATH
    assert signal.url == "https://www.acme.com/careers"
    assert signal.text == "Careers"


def test_nav_link_text_without_hiring_path_is_a_signal():
    html = page('<nav><a href="/equipo">Trabaja con nosotros</a></nav>')

    signal = detect_hiring_signal(html, PAGE_URL)

    assert signal.kind == HiringSignalKind.LINK_TEXT
    assert signal.url == "https://www.acme.com/equipo"


def test_link_to_job_board_is_a_signal():
    html = page('<a href="https://boards.greenhouse.io/acme">See roles</a>')

    signal = detect_hiring_signal(html, PAGE_URL)

    assert signal.kind == HiringSignalKind.JOB_BOARD
    assert signal.url == "https://boards.greenhouse.io/acme"


def test_jobs_section_of_linkedin_or_yc_is_a_job_board():
    linkedin = page('<a href="https://www.linkedin.com/company/acme/jobs/">Open roles</a>')
    yc = page('<a href="https://www.ycombinator.com/companies/acme/jobs">Work at Acme</a>')

    assert detect_hiring_signal(linkedin, PAGE_URL).kind == HiringSignalKind.JOB_BOARD
    assert detect_hiring_signal(yc, PAGE_URL).kind == HiringSignalKind.JOB_BOARD


def test_plain_linkedin_company_page_is_not_a_signal():
    html = page('<a href="https://www.linkedin.com/company/acme/">LinkedIn</a>')

    assert detect_hiring_signal(html, PAGE_URL) is None


def test_hiring_phrase_in_visible_text_is_a_signal():
    html = page("<section><h2>We’re hiring!</h2><p>Come build with us.</p></section>")

    signal = detect_hiring_signal(html, PAGE_URL)

    assert signal.kind == HiringSignalKind.PHRASE
    assert signal.url == PAGE_URL
    assert "hiring" in signal.text.lower()


def test_jobs_email_address_is_a_signal():
    html = page('<a href="mailto:jobs@acme.com">Write to us</a>')

    signal = detect_hiring_signal(html, PAGE_URL)

    assert signal.kind == HiringSignalKind.EMAIL
    assert signal.url == "mailto:jobs@acme.com"


def test_join_us_on_discord_or_waitlist_is_not_a_signal():
    html = page(
        '<a href="https://discord.gg/acme">Join us on Discord</a>'
        '<a href="/waitlist">Join the waitlist</a>'
        '<a href="/community">Join us</a>'
    )

    assert detect_hiring_signal(html, PAGE_URL) is None


def test_join_us_linking_to_a_hiring_path_is_a_signal():
    html = page('<a href="/join-us">Join us</a>')

    assert detect_hiring_signal(html, PAGE_URL).kind == HiringSignalKind.LINK_PATH


def test_single_words_only_count_as_whole_link_text():
    html = page('<a href="/blog/steve">What Steve Jobs taught us</a><p>Jobs to be done</p>')

    assert detect_hiring_signal(html, PAGE_URL) is None


def test_hiring_path_on_another_site_is_not_a_signal():
    html = page('<a href="https://otherco.com/careers">A friend of ours</a>')

    assert detect_hiring_signal(html, PAGE_URL) is None


def test_text_inside_scripts_and_styles_is_ignored():
    html = page('<script>const banner = "We\'re hiring";</script><style>.jobs{}</style>')

    assert detect_hiring_signal(html, PAGE_URL) is None


def test_strongest_signal_wins():
    html = page(
        "<p>We are hiring!</p>"
        '<a href="/careers">Careers</a>'
        '<a href="https://jobs.lever.co/acme">Openings</a>'
    )

    assert detect_hiring_signal(html, PAGE_URL).kind == HiringSignalKind.JOB_BOARD


def test_visible_text_is_normalized_for_comparison():
    assert visible_text(page("<p>  Hello\n  <b>World</b> </p><script>x</script>")) == (
        "acme hello world"
    )


def test_hiring_words_inside_documentation_paths_are_not_a_signal():
    html = page(
        '<a href="/docs/applications/jobs/">Jobs and Deploy Hooks</a>'
        '<a href="/es/docs/careers">Guide</a>'
    )

    assert detect_hiring_signal(html, PAGE_URL) is None


def test_careers_page_nested_in_a_company_section_is_a_signal():
    html = page('<a href="/company/careers">Careers</a>')

    assert detect_hiring_signal(html, PAGE_URL).kind == HiringSignalKind.LINK_PATH
