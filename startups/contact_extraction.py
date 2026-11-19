"""Finds, in a page of the startup's own website, the people and mailboxes to contact.

Pure functions with deterministic rules, no AI: mailto links and emails of the site's own domain,
LinkedIn profile links (only the URL is kept; LinkedIn is never visited), schema.org JSON-LD
people, and names next to job titles such as "CEO" or "Co-founder". It is a heuristic: many
sites do not publish their team.
"""

import json
from dataclasses import dataclass, replace
from urllib.parse import unquote, urljoin, urlsplit

from bs4 import BeautifulSoup

from startups.constants import (
    CONTACT_PAGE_SLUGS,
    CONTACT_ROLE_STRENGTH,
    EMAIL_PATTERN,
    GENERAL_EMAIL_LOCAL_PARTS,
    HIRING_EMAIL_LOCAL_PARTS,
    JOB_TITLE_COMPANY_MARKER_PATTERN,
    JOB_TITLE_COMPANY_MARKERS,
    JSON_LD_FOUNDER_KEY,
    JSON_LD_PERSON_TYPE,
    JSON_LD_SCRIPT_TYPE,
    JSON_LD_TEAM_KEYS,
    JSON_LD_WORKS_FOR_KEY,
    LINKEDIN_DOMAIN,
    LINKEDIN_PROFILE_PATH_PREFIX,
    MAILTO_SCHEME,
    NAME_LOOKBEHIND_FRAGMENTS,
    NAME_ROLE_SEPARATOR_PATTERN,
    NON_TEAM_SECTION_PHRASES,
    NON_VISIBLE_HTML_TAGS,
    NOT_NAME_WORDS,
    PERSON_NAME_MAX_LENGTH,
    PERSON_NAME_MAX_WORDS,
    PERSON_NAME_MIN_WORDS,
    PERSON_NAME_WORD_PATTERN,
    ROLE_LINE_MAX_WORDS,
    ROLE_TITLE_PHRASES,
    SECTION_HEADING_LOOKBEHIND,
    SECTION_HEADING_TAGS,
    ContactRole,
)
from startups.domains import domain_matches_name, normalize_domain
from startups.exceptions import InvalidWebsiteError
from startups.hiring_signal import normalize_text


@dataclass(frozen=True)
class ContactCandidate:
    full_name: str
    role: str
    email: str
    profile_url: str
    evidence_url: str


def extract_contacts(html, page_url):
    """Contacts published on the page, merged so that each person or mailbox appears once."""
    soup = BeautifulSoup(html, "html.parser")
    json_ld_blocks = [
        script.get_text() for script in soup.find_all("script", type=JSON_LD_SCRIPT_TYPE)
    ]
    for element in soup(NON_VISIBLE_HTML_TAGS):
        element.decompose()
    site_domain = _domain_or_none(page_url)
    candidates = [
        *_json_ld_people(json_ld_blocks, site_domain, page_url),
        *_people_next_to_job_titles(soup, site_domain, page_url),
        *_email_contacts(soup, site_domain, page_url),
        *_linkedin_profiles(soup, page_url),
    ]
    return merge_contacts(candidates)


def contact_page_links(html, page_url):
    """Links of the same site to about, team or contact pages, in order of appearance."""
    soup = BeautifulSoup(html, "html.parser")
    site_domain = _domain_or_none(page_url)
    links = []
    for link in soup.find_all("a", href=True):
        absolute_url = urljoin(page_url, link["href"].strip())
        parts = urlsplit(absolute_url)
        if _domain_or_none(absolute_url) != site_domain:
            continue
        segments = [segment for segment in parts.path.lower().split("/") if segment]
        if not segments or segments[-1] not in CONTACT_PAGE_SLUGS:
            continue
        clean_url = f"{parts.scheme}://{parts.netloc}{parts.path}"
        if clean_url not in links:
            links.append(clean_url)
    return links


def role_from_title(title):
    """The role a job title states (`CEO & Co-founder` -> CEO), or None."""
    normalized_title = normalize_text(title or "")
    for role, phrases in ROLE_TITLE_PHRASES:
        if any(_contains_phrase(normalized_title, phrase) for phrase in phrases):
            return role
    return None


def _json_ld_people(json_ld_blocks, site_domain, page_url):
    """People the organization lists as its own (founder, employee, member)."""
    for block in json_ld_blocks:
        try:
            data = json.loads(block)
        except ValueError:
            continue
        for person, parent_key in _walk_json_ld(data, parent_key=""):
            if parent_key not in JSON_LD_TEAM_KEYS:
                continue  # A review author or a quoted customer.
            name = str(person.get("name") or "").strip()
            job_title = str(person.get("jobTitle") or "")
            role = role_from_title(job_title)
            if role is None and parent_key == JSON_LD_FOUNDER_KEY:
                role = ContactRole.FOUNDER
            if not name or role is None:
                continue
            if _names_another_company(job_title, site_domain) or _works_elsewhere(
                person.get(JSON_LD_WORKS_FOR_KEY), site_domain
            ):
                continue
            yield ContactCandidate(
                full_name=name,
                role=role,
                email=_email_from(str(person.get("email") or "")),
                profile_url=_linkedin_profile_in(person.get("sameAs")),
                evidence_url=page_url,
            )


def _walk_json_ld(node, parent_key):
    """Every schema.org Person in a JSON-LD document, with the key it was found under."""
    if isinstance(node, list):
        for item in node:
            yield from _walk_json_ld(item, parent_key)
        return
    if not isinstance(node, dict):
        return
    node_types = node.get("@type")
    node_types = node_types if isinstance(node_types, list) else [node_types]
    if JSON_LD_PERSON_TYPE in node_types:
        yield node, parent_key
    for key, value in node.items():
        yield from _walk_json_ld(value, key)


def _people_next_to_job_titles(soup, site_domain, page_url):
    """`<h3>Jane Roe</h3><p>CEO</p>` (team cards) and `Jane Roe, Founder` (one line).

    A job title at another company ("CEO at Globex") is a customer quote, not the team.
    """
    for text_node in soup.find_all(string=True):
        line = " ".join(text_node.split())
        if not line or len(line.split()) > ROLE_LINE_MAX_WORDS:
            continue
        name, role, title = _name_and_role_in_line(line)
        name_node = text_node
        if role is None:
            role = role_from_title(line)
            if role is None:
                continue
            title = line
            name_node = _name_before(text_node)
            name = " ".join(name_node.split()) if name_node is not None else ""
        if not name or _names_another_company(title, site_domain):
            continue
        if _company_after_title(text_node, site_domain) or _in_non_team_section(text_node):
            continue
        container = _common_container(text_node, name_node)
        yield ContactCandidate(
            full_name=name,
            role=role,
            email="",
            profile_url=_linkedin_profile_in_container(container),
            evidence_url=page_url,
        )


def _name_and_role_in_line(line):
    """`Built by Jane Roe, Founder` -> (`Jane Roe`, FOUNDER, `Founder`); blanks if not that."""
    parts = NAME_ROLE_SEPARATOR_PATTERN.split(line, maxsplit=1)
    if len(parts) != 2:
        return "", None, ""
    before_separator, after_separator = parts
    role = role_from_title(after_separator)
    if role is None:
        return "", None, ""
    name = _trailing_name(before_separator)
    return (name, role, after_separator) if name else ("", None, "")


def _names_another_company(title, site_domain):
    """`CEO at Globex` on acme.com -> True; `CEO at Acme`, `Co-founder, CTO` -> False."""
    company = JOB_TITLE_COMPANY_MARKER_PATTERN.split(title)[-1].strip()
    if not company or company == title.strip() or role_from_title(company) is not None:
        return False
    return site_domain is None or not domain_matches_name(site_domain, company)


def _works_elsewhere(works_for, site_domain):
    if not isinstance(works_for, dict) or not works_for.get("name"):
        return False
    return site_domain is None or not domain_matches_name(site_domain, str(works_for["name"]))


def _company_after_title(title_node, site_domain):
    """`Co-founder` `at` `Globex` in separate fragments: True when Globex is not the startup."""
    next_fragments = []
    for next_node in title_node.find_all_next(string=True):
        fragment = " ".join(next_node.split())
        if fragment:
            next_fragments.append(fragment)
        if len(next_fragments) == 2:
            break
    if len(next_fragments) < 2 or next_fragments[0].lower() not in JOB_TITLE_COMPANY_MARKERS:
        return False
    return site_domain is None or not domain_matches_name(site_domain, next_fragments[1])


def _in_non_team_section(text_node):
    """Under a heading such as "Backed by", "Investors" or "What our customers say"."""
    for heading in text_node.find_all_previous(
        SECTION_HEADING_TAGS, limit=SECTION_HEADING_LOOKBEHIND
    ):
        heading_text = " ".join(heading.get_text(" ").split())
        if _is_person_name(heading_text):
            continue  # The name of a team card, not a section.
        normalized_heading = normalize_text(heading_text)
        return any(
            _contains_phrase(normalized_heading, phrase) for phrase in NON_TEAM_SECTION_PHRASES
        )
    return False


def _trailing_name(text):
    """The capitalized words at the end of `text` if they look like a person's name."""
    name_words = []
    for word in reversed(text.split()):
        if not _is_name_word(word) or len(name_words) == PERSON_NAME_MAX_WORDS:
            break
        name_words.insert(0, word)
    name = " ".join(name_words)
    return name if _is_person_name(name) else ""


def _name_before(text_node):
    """The closest earlier text fragment that is a person's name, within a few fragments."""
    previous_fragments = 0
    for previous_node in text_node.find_all_previous(string=True):
        fragment = " ".join(previous_node.split())
        if not fragment:
            continue
        if _is_person_name(fragment):
            return previous_node
        previous_fragments += 1
        if previous_fragments == NAME_LOOKBEHIND_FRAGMENTS:
            return None
    return None


def _is_person_name(text):
    words = text.split()
    return (
        PERSON_NAME_MIN_WORDS <= len(words) <= PERSON_NAME_MAX_WORDS
        and len(text) <= PERSON_NAME_MAX_LENGTH
        and all(_is_name_word(word) for word in words)
        and role_from_title(text) is None
    )


def _is_name_word(word):
    return (
        bool(PERSON_NAME_WORD_PATTERN.match(word))
        and word[0].isupper()
        and word.lower() not in NOT_NAME_WORDS
    )


def _common_container(first_node, second_node):
    """The smallest element holding both text fragments (a team card), or the first's parent."""
    for ancestor in first_node.parents:
        if second_node is first_node or second_node in ancestor.descendants:
            return ancestor
    return first_node.parent


def _linkedin_profile_in_container(container):
    if container is None:
        return ""
    profiles = [
        link["href"].strip()
        for link in container.find_all("a", href=True)
        if _is_linkedin_profile(link["href"].strip())
    ]
    # A container with several profiles is the whole team, not one person's card.
    return profiles[0] if len(profiles) == 1 else ""


def _email_contacts(soup, site_domain, page_url):
    for link in soup.find_all("a", href=True):
        href = link["href"].strip()
        if href.lower().startswith(MAILTO_SCHEME):
            link_text = " ".join(link.get_text(" ").split())
            candidate = _email_candidate(_email_from(href), site_domain, link_text, page_url)
            if candidate is not None:
                yield candidate
    for address in EMAIL_PATTERN.findall(soup.get_text(" ")):
        candidate = _email_candidate(address.lower(), site_domain, "", page_url)
        if candidate is not None:
            yield candidate


def _email_candidate(email, site_domain, link_text, page_url):
    """Only mailboxes of the site's own domain, and not the hiring ones (jobs@, careers@)."""
    if "@" not in email:
        return None
    local_part, email_domain = email.rsplit("@", 1)
    if site_domain is None or _domain_or_none(email_domain) != site_domain:
        return None
    if local_part in HIRING_EMAIL_LOCAL_PARTS:
        return None
    if local_part in GENERAL_EMAIL_LOCAL_PARTS:
        return ContactCandidate("", ContactRole.GENERAL, email, "", page_url)
    full_name = link_text if _is_person_name(link_text) else ""
    return ContactCandidate(full_name, ContactRole.OTHER, email, "", page_url)


def _linkedin_profiles(soup, page_url):
    for link in soup.find_all("a", href=True):
        href = link["href"].strip()
        if not _is_linkedin_profile(href):
            continue
        link_text = " ".join(link.get_text(" ").split())
        full_name = link_text if _is_person_name(link_text) else ""
        yield ContactCandidate(full_name, ContactRole.OTHER, "", href, page_url)


def _is_linkedin_profile(url):
    parts = urlsplit(url)
    return _domain_or_none(url) == LINKEDIN_DOMAIN and parts.path.startswith(
        LINKEDIN_PROFILE_PATH_PREFIX
    )


def _linkedin_profile_in(same_as):
    urls = same_as if isinstance(same_as, list) else [same_as]
    for url in urls:
        if isinstance(url, str) and _is_linkedin_profile(url):
            return url
    return ""


def _email_from(value):
    """`mailto:Jane@Acme.com?subject=Hi` -> `jane@acme.com`."""
    address = value.strip()
    if address.lower().startswith(MAILTO_SCHEME):
        address = address[len(MAILTO_SCHEME) :]
    return unquote(address.split("?")[0]).strip().lower()


def merge_contacts(candidates):
    """One contact per person or mailbox: same email, same profile or same name."""
    merged = []
    for candidate in candidates:
        match_position = next(
            (
                position
                for position, existing in enumerate(merged)
                if _is_same_contact(existing, candidate)
            ),
            None,
        )
        if match_position is None:
            merged.append(candidate)
        else:
            merged[match_position] = _combine(merged[match_position], candidate)
    return merged


def _is_same_contact(first, second):
    return (
        (first.email and first.email == second.email)
        or (first.profile_url and first.profile_url == second.profile_url)
        or (first.full_name and first.full_name.lower() == second.full_name.lower())
    )


def _combine(first, second):
    strongest_role = min(first.role, second.role, key=CONTACT_ROLE_STRENGTH.index)
    return replace(
        first,
        full_name=first.full_name or second.full_name,
        role=strongest_role,
        email=first.email or second.email,
        profile_url=first.profile_url or second.profile_url,
    )


def _contains_phrase(normalized_text, phrase):
    return f" {phrase} " in f" {normalized_text} "


def _domain_or_none(url):
    try:
        return normalize_domain(url)
    except InvalidWebsiteError:
        return None
