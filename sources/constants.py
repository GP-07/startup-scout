import re

from django.db import models


class SourceKey(models.TextChoices):
    """Stable source identifiers: stored in the database, mapped to adapters in memory."""

    HACKER_NEWS = "hacker_news", "Hacker News"
    HACKER_NEWS_HIRING = "hacker_news_hiring", "HN Who is hiring"
    MANUAL = "manual", "Alta manual"


class SourceRunStatus(models.TextChoices):
    RUNNING = "running", "En curso"
    SUCCEEDED = "succeeded", "OK"
    FAILED = "failed", "Con error"


HTTP_TIMEOUT_SECONDS = 20
HTTP_USER_AGENT = "startup-scout/0.1"

# Daily discovery (Europe/Madrid, the project's TIME_ZONE).
DISCOVERY_HOUR = 7
DISCOVERY_MINUTE = 0
SOURCE_RUN_LOCK_PREFIX = "source-run"

# Hacker News, through the public Algolia API.
HACKER_NEWS_SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
HACKER_NEWS_ITEM_URL = "https://news.ycombinator.com/item?id={item_id}"
HACKER_NEWS_USER_URL = "https://news.ycombinator.com/user?id={author}"
HACKER_NEWS_PAGE_SIZE = 100
HACKER_NEWS_INITIAL_LOOKBACK_DAYS = 7
HACKER_NEWS_DESCRIPTION_MAX_LENGTH = 500
HACKER_NEWS_CURSOR_KEY = "last_created_at_i"
HACKER_NEWS_CURSOR_OVERLAP_SECONDS = 3600
HACKER_NEWS_IGNORED_PAYLOAD_KEYS = frozenset({"_highlightResult"})

# Each configurable tag maps to the Algolia query that finds it and the title prefix it must have.
# "Launch HN" has no Algolia tag: it is searched as text and filtered by title.
HACKER_NEWS_QUERIES = {
    "show_hn": {"params": {"tags": "show_hn"}, "title_prefix": "Show HN:"},
    "launch_hn": {
        "params": {"tags": "story", "query": '"Launch HN"'},
        "title_prefix": "Launch HN:",
    },
}

# Separators between the product name and its tagline in a post title.
HACKER_NEWS_TITLE_SEPARATORS = (" – ", " — ", " - ", ", ", ": ")
# "(YC F26)" after a Launch HN product name.
YC_BATCH_PATTERN = re.compile(r"\s*\(YC [A-Z]\d{2}\)\s*$")
HTML_LINK_PATTERN = re.compile(r'href="([^"]+)"')
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
WHITESPACE_PATTERN = re.compile(r"\s+")

# Hacker News "Ask HN: Who is hiring?": a monthly thread where each top-level comment is a job post.
HACKER_NEWS_HIRING_THREAD_TAGS = "story,author_whoishiring"
HACKER_NEWS_HIRING_THREAD_TITLE_PREFIX = "Ask HN: Who is hiring?"
HACKER_NEWS_HIRING_COMMENT_TAGS = "comment,story_{thread_id}"
# Comments keep arriving after the 1st of the month: threads this recent are read again daily.
HACKER_NEWS_HIRING_THREAD_MAX_AGE_DAYS = 45
# On the first run, how many of the newest threads to read in full.
HACKER_NEWS_HIRING_INITIAL_THREADS = 1
# Job posts start with a header such as `Acme | Backend Engineer | Berlin | REMOTE`.
HACKER_NEWS_HIRING_HEADER_SEPARATOR = "|"
HTML_PARAGRAPH_PATTERN = re.compile(r"<p>", re.IGNORECASE)
PARENTHESIZED_TEXT_PATTERN = re.compile(r"\([^)]*\)")
EMAIL_ADDRESS_PATTERN = re.compile(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")
DEFAULT_WEBSITE_SCHEME = "https://"
# Mailbox providers: an address there says nothing about the company's own domain.
FREE_EMAIL_DOMAINS = frozenset(
    {
        "aol.com",
        "fastmail.com",
        "gmail.com",
        "gmx.com",
        "gmx.de",
        "googlemail.com",
        "hey.com",
        "hotmail.com",
        "icloud.com",
        "live.com",
        "mail.com",
        "me.com",
        "outlook.com",
        "pm.me",
        "proton.me",
        "protonmail.com",
        "yahoo.com",
        "yandex.com",
        "zoho.com",
    }
)
