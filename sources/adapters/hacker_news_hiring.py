import html
import logging
from datetime import timedelta

from django.utils import timezone

from sources.adapters.algolia import created_after_filter, fetch_algolia_hits
from sources.adapters.base import RawStartup, SourceAdapter, SourceFetchResult
from sources.adapters.html_text import (
    extract_links,
    identifying_domain,
    plain_text,
    timestamp_to_datetime,
)
from sources.constants import (
    COMPANY_NAME_MATCH_MIN_LENGTH,
    DEFAULT_WEBSITE_SCHEME,
    EMAIL_ADDRESS_PATTERN,
    FREE_EMAIL_DOMAINS,
    HACKER_NEWS_CURSOR_KEY,
    HACKER_NEWS_CURSOR_OVERLAP_SECONDS,
    HACKER_NEWS_DESCRIPTION_MAX_LENGTH,
    HACKER_NEWS_HIRING_COMMENT_TAGS,
    HACKER_NEWS_HIRING_HEADER_SEPARATOR,
    HACKER_NEWS_HIRING_INITIAL_THREADS,
    HACKER_NEWS_HIRING_THREAD_MAX_AGE_DAYS,
    HACKER_NEWS_HIRING_THREAD_TAGS,
    HACKER_NEWS_HIRING_THREAD_TITLE_PREFIX,
    HACKER_NEWS_IGNORED_PAYLOAD_KEYS,
    HACKER_NEWS_ITEM_URL,
    HTML_PARAGRAPH_PATTERN,
    PARENTHESIZED_TEXT_PATTERN,
    WHITESPACE_PATTERN,
)
from startups.domains import normalize_name

logger = logging.getLogger(__name__)


class HackerNewsHiringAdapter(SourceAdapter):
    """Reads the job posts of the monthly "Ask HN: Who is hiring?" threads.

    Each top-level comment is one company hiring; replies are conversations and are skipped.
    A post only becomes a startup when its own website can be told apart from the job boards,
    press and forms it links to (see `_choose_website`).

    Config: optionally `initial_threads` (how many of the newest threads the first run reads).
    Cursor: `created_at_i` of the newest comment seen.
    """

    def fetch_candidates(self, cursor):
        last_seen_timestamp = cursor.get(HACKER_NEWS_CURSOR_KEY)
        threads = self._recent_threads()
        if last_seen_timestamp:
            # Algolia can index a comment late: re-read a short window. Repeats are just updates.
            since_timestamp = last_seen_timestamp - HACKER_NEWS_CURSOR_OVERLAP_SECONDS
        else:
            since_timestamp = None
            threads = threads[
                : self.config.get("initial_threads", HACKER_NEWS_HIRING_INITIAL_THREADS)
            ]

        newest_timestamp = last_seen_timestamp or 0
        raw_startups_by_id = {}
        skipped_posts = 0
        for thread in threads:
            for comment in self._fetch_comments(thread, since_timestamp):
                newest_timestamp = max(newest_timestamp, comment["created_at_i"])
                if str(comment.get("parent_id")) != str(thread["objectID"]):
                    continue  # A reply to a job post.
                raw_startup = _to_raw_startup(comment)
                if raw_startup is None:
                    skipped_posts += 1
                    continue
                raw_startups_by_id[raw_startup.external_id] = raw_startup
        logger.info(
            "Who is hiring: %s posts with a company website, %s skipped",
            len(raw_startups_by_id),
            skipped_posts,
        )
        cursor = {HACKER_NEWS_CURSOR_KEY: newest_timestamp} if newest_timestamp else {}
        return SourceFetchResult(raw_startups=list(raw_startups_by_id.values()), cursor=cursor)

    def _recent_threads(self):
        """ "Who is hiring?" threads of the last weeks, newest first."""
        oldest_thread_date = timezone.now() - timedelta(days=HACKER_NEWS_HIRING_THREAD_MAX_AGE_DAYS)
        query_params = {
            "tags": HACKER_NEWS_HIRING_THREAD_TAGS,
            "numericFilters": created_after_filter(int(oldest_thread_date.timestamp())),
        }
        threads = [
            hit
            for hit in fetch_algolia_hits(self.http_client, query_params)
            if (hit.get("title") or "").startswith(HACKER_NEWS_HIRING_THREAD_TITLE_PREFIX)
        ]
        return sorted(threads, key=_created_at, reverse=True)

    def _fetch_comments(self, thread, since_timestamp):
        query_params = {
            "tags": HACKER_NEWS_HIRING_COMMENT_TAGS.format(thread_id=thread["objectID"])
        }
        if since_timestamp is not None:
            query_params["numericFilters"] = created_after_filter(since_timestamp)
        return fetch_algolia_hits(self.http_client, query_params)


def _to_raw_startup(comment):
    """The company behind a job post, or None if it has no header or no own website."""
    comment_html = comment.get("comment_text") or ""
    header_html = HTML_PARAGRAPH_PATTERN.split(comment_html, maxsplit=1)[0]
    header = plain_text(header_html)
    if HACKER_NEWS_HIRING_HEADER_SEPARATOR not in header:
        return None
    name = _company_name(header)
    website = _choose_website(name, comment_html, header_html)
    if not name or not website:
        return None
    return RawStartup(
        external_id=str(comment["objectID"]),
        url=HACKER_NEWS_ITEM_URL.format(item_id=comment["objectID"]),
        name=name,
        website=website,
        description=header[:HACKER_NEWS_DESCRIPTION_MAX_LENGTH],
        published_at=timestamp_to_datetime(comment.get("created_at_i")),
        raw_payload={
            key: value
            for key, value in comment.items()
            if key not in HACKER_NEWS_IGNORED_PAYLOAD_KEYS
        },
    )


def _company_name(header):
    """`Acme Labs (YC W26) | Backend Engineer | Berlin` -> `Acme Labs`."""
    first_segment = header.split(HACKER_NEWS_HIRING_HEADER_SEPARATOR, maxsplit=1)[0]
    without_parentheses = PARENTHESIZED_TEXT_PATTERN.sub(" ", first_segment)
    return WHITESPACE_PATTERN.sub(" ", without_parentheses).strip()


def _choose_website(name, comment_html, header_html):
    """The company's own website, by decreasing confidence; None if none can be told apart.

    1. A link whose domain matches the company name.
    2. A link in the header line, where the post convention puts the company URL.
    3. The domain of an email address in the post, unless it is a mailbox provider.

    Any other link (press articles, forms, papers) could belong to someone else, and taking it
    would merge unrelated companies under one domain.
    """
    own_links = [link for link in extract_links(comment_html) if identifying_domain(link)]
    for link in own_links:
        if _matches_company_name(identifying_domain(link), name):
            return link
    for link in extract_links(header_html):
        if identifying_domain(link):
            return link
    for email_domain in EMAIL_ADDRESS_PATTERN.findall(html.unescape(plain_text(comment_html))):
        email_domain = email_domain.lower().rstrip(".")
        if email_domain in FREE_EMAIL_DOMAINS:
            continue
        domain = identifying_domain(email_domain)
        if domain:
            return DEFAULT_WEBSITE_SCHEME + domain
    return None


def _matches_company_name(domain, name):
    """`lumbrelabs.com` matches "Lumbre Labs"; `acmehq.com` matches "Acme"."""
    domain_label = domain.split(".")[0].replace("-", "")
    name_words = normalize_name(name).split()
    if not name_words:
        return False
    joined_name = "".join(name_words)
    first_word = name_words[0]
    return (
        domain_label == joined_name
        or (len(first_word) >= COMPANY_NAME_MATCH_MIN_LENGTH and first_word in domain_label)
        or (len(domain_label) >= COMPANY_NAME_MATCH_MIN_LENGTH and domain_label in joined_name)
    )


def _created_at(hit):
    return hit["created_at_i"]
