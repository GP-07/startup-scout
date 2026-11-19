import re

from django.db import models

from sources.constants import SourceKey


class StartupStatus(models.TextChoices):
    NEW = "new", "Nueva"
    REVIEWING = "reviewing", "En revisión"
    ANALYZING = "analyzing", "Analizando"
    READY_TO_CONTACT = "ready_to_contact", "Lista para contactar"
    CONTACTED = "contacted", "Contactada"
    REPLIED = "replied", "Respondió"
    DISCARDED = "discarded", "Descartada"


class RemotePolicy(models.TextChoices):
    UNKNOWN = "unknown", "Desconocido"
    REMOTE = "remote", "Remoto"
    HYBRID = "hybrid", "Híbrido"
    ONSITE = "onsite", "Presencial"


class ContactRole(models.TextChoices):
    CEO = "ceo", "CEO"
    CTO = "cto", "CTO"
    FOUNDER = "founder", "Founder"
    OTHER = "other", "Otro cargo"
    GENERAL = "general", "Contacto general"


class ContactFoundVia(models.TextChoices):
    SOURCE = "source", "Fuente"
    WEBSITE = "website", "Web de la startup"
    MANUAL = "manual", "Manual"


class ContactStatus(models.TextChoices):
    CANDIDATE = "candidate", "Candidato"
    CONFIRMED = "confirmed", "Confirmado"
    REJECTED = "rejected", "Descartado"


# Fields of `Startup` recomputed from the source records.
MERGEABLE_FIELDS = ("name", "website", "description", "country", "city")

# First source with a non-blank value wins. Sources not listed here go last.
SOURCE_MERGE_PRIORITY = (
    SourceKey.MANUAL,
    SourceKey.HACKER_NEWS,
    # A job post header ("Acme | Backend Engineer | Berlin") describes the job, not the product.
    SourceKey.HACKER_NEWS_HIRING,
)

# Tokens dropped from the end of a company name before comparing names.
LEGAL_NAME_SUFFIXES = frozenset(
    {
        "ab",
        "bv",
        "co",
        "corp",
        "gmbh",
        "inc",
        "limited",
        "llc",
        "ltd",
        "oy",
        "plc",
        "sa",
        "sas",
        "sau",
        "sl",
        "sll",
        "slu",
        "srl",
    }
)

# Hiring platforms: any link to them is a signal.
JOB_BOARD_DOMAINS = frozenset(
    {
        "ashbyhq.com",
        "bamboohr.com",
        "breezy.hr",
        "greenhouse.io",
        "grnh.se",
        "icims.com",
        "jobvite.com",
        "join.com",
        "lever.co",
        "myworkdayjobs.com",
        "personio.com",
        "personio.de",
        "recruitee.com",
        "smartrecruiters.com",
        "teamtailor.com",
        "welcometothejungle.com",
        "workable.com",
        "workatastartup.com",
    }
)

# Platforms whose links point to content inside them (a repository, an app store page, a profile):
# their domain says nothing about which startup it is, so it is never used as identity.
CONTENT_PLATFORM_DOMAINS = frozenset(
    {
        "apple.com",
        "archive.org",
        "arxiv.org",
        "atlassian.com",
        "bitbucket.org",
        "bolt.new",
        "cloudflare.com",
        "crates.io",
        "dev.to",
        "discord.com",
        "discord.gg",
        "facebook.com",
        "figma.com",
        "github.com",
        "gitlab.com",
        "google.com",
        "huggingface.co",
        "instagram.com",
        "jetbrains.com",
        "kaggle.com",
        "linkedin.com",
        "loom.com",
        "microsoft.com",
        "mozilla.org",
        "notion.so",
        "npmjs.com",
        "producthunt.com",
        "pypi.org",
        "reddit.com",
        "shopify.com",
        "slack.com",
        "sourceforge.net",
        "t.me",
        "tiktok.com",
        "twitter.com",
        "vercel.com",
        "visualstudio.com",
        "wikipedia.org",
        "x.com",
        "ycombinator.com",
        "youtu.be",
        "youtube.com",
        "zapier.com",
        # Linked from job posts: forms, press and archives say nothing about who is hiring.
        "airtable.com",
        "archive.ph",
        "bloomberg.com",
        "businessinsider.com",
        "calendly.com",
        "forbes.com",
        "forms.gle",
        "nytimes.com",
        "oraclecloud.com",
        "reuters.com",
        "tally.so",
        "techcrunch.com",
        "typeform.com",
        "wsj.com",
    }
)
# Never used as identity. Job boards host the openings of many companies, so they are included.
NON_IDENTIFYING_DOMAINS = CONTENT_PLATFORM_DOMAINS | JOB_BOARD_DOMAINS

# Hosts that give each customer a subdomain but are missing from the Public Suffix List:
# `acme.substack.com` identifies Acme, while `substack.com` alone identifies nobody.
SHARED_HOST_DOMAINS = frozenset(
    {
        "bolt.host",
        "gitbook.io",
        "hashnode.dev",
        "itch.io",
        "medium.com",
        "substack.com",
        "wixsite.com",
        "wordpress.com",
    }
)
WWW_SUBDOMAIN = "www"

# Attempts to ingest one startup when concurrent ingestions collide on a unique constraint.
MAX_INGESTION_ATTEMPTS = 3

REDIRECT_TIMEOUT_SECONDS = 10
REDIRECT_USER_AGENT = "startup-scout/0.1"
# Some servers reject HEAD requests: retry those with GET.
HEAD_FALLBACK_STATUS_CODES = frozenset({403, 405, 501})

DEFAULT_URL_SCHEME = "https://"
URL_SCHEME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")
NON_ALPHANUMERIC_PATTERN = re.compile(r"[^a-z0-9]+")


# Website inspection: hiring signal (see docs/startup-scout-design.md §3).
class InspectionStatus(models.TextChoices):
    PENDING = "pending", "Pendiente"
    DONE = "done", "Inspeccionada"
    BLOCKED = "blocked", "Bloqueada por robots.txt"
    FAILED = "failed", "Con error"


# A "Who is hiring?" post counts as a hiring signal for this long after it was published.
HIRING_POST_MAX_AGE_DAYS = 60


class HiringSignalOrigin(models.TextChoices):
    WEBSITE = "website", "Web"
    HIRING_POST = "hiring_post", "Who is hiring"
    BOTH = "both", "Web + Who is hiring"


# Admin filter of startups by hiring signal.
HIRING_FILTER_PARAMETER = "hiring_signal"
HIRING_FILTER_YES = "yes"
HIRING_FILTER_NO = "no"


class HiringSignalMethod(models.TextChoices):
    HOME = "home", "Home"
    PATH_PROBE = "path_probe", "Ruta típica"


class HiringSignalKind(models.TextChoices):
    """Ordered from strongest to weakest: the strongest signal found on a page wins."""

    JOB_BOARD = "job_board", "Plataforma de búsqueda"
    LINK_PATH = "link_path", "Link a una ruta de búsqueda"
    LINK_TEXT = "link_text", "Texto de link"
    EMAIL = "email", "Mail de búsqueda"
    PHRASE = "phrase", "Frase en el texto"


HIRING_SIGNAL_KIND_PRIORITY = tuple(HiringSignalKind)

INSPECTION_TIMEOUT_SECONDS = 10
INSPECTION_USER_AGENT = "startup-scout/0.1"
# Name matched against `User-agent:` lines in robots.txt.
ROBOTS_USER_AGENT_TOKEN = "startup-scout"
ROBOTS_TXT_PATH = "/robots.txt"
HTML_CONTENT_TYPE = "text/html"
HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_SERVER_ERROR_MIN = 500
# robots.txt answered with these codes means the site disallows everything.
ROBOTS_DISALLOW_ALL_STATUS_CODES = frozenset({401, 403})
HOME_PATHS = frozenset({"", "/"})
HIRING_SIGNAL_TEXT_MAX_LENGTH = 200

# Tried in order, only when the home page shows no signal. Stops at the first one with a signal.
HIRING_FALLBACK_PATHS = ("/careers", "/jobs", "/join-us", "/trabaja-con-nosotros")
# `inspect_websites` skips these unless --all; pending and failed ones are inspected again.
ALREADY_INSPECTED_STATUSES = (InspectionStatus.DONE, InspectionStatus.BLOCKED)
INSPECTION_PROGRESS_EVERY = 25

# Probable single-page-app shells (startups/page_metrics.py): thresholds to review by hand.
SPA_SHELL_MAX_TEXT_LENGTH = 200
SPA_SHELL_MIN_LINK_COUNT = 3
# Elements where React, Vue, Next.js, Nuxt, Gatsby and similar mount the app.
APP_ROOT_ELEMENT_IDS = ["root", "app", "__next", "__nuxt", "___gatsby", "svelte"]

# A path segment like these in a same-site link is a signal: /careers, /about/jobs/, /es/empleo.
HIRING_PATH_PATTERN = re.compile(
    r"(^|/)(careers?|jobs|join-us|join-the-team|join-our-team|work-with-us|open-positions"
    r"|empleo|empleos|trabaja-con-nosotros|unete|vacantes)(/|$)"
)

# Same-site links under these sections are never a signal: `/docs/.../jobs` means batch jobs.
HIRING_PATH_EXCLUDED_SECTIONS = frozenset(
    {
        "api",
        "blog",
        "changelog",
        "docs",
        "documentation",
        "guide",
        "guides",
        "help",
        "reference",
        "support",
    }
)

# Whole link texts (normalized: lowercase, no accents, no punctuation).
HIRING_LINK_WORDS = frozenset({"career", "careers", "jobs", "empleo", "empleos", "vacantes"})
# Link texts containing any of these phrases.
HIRING_LINK_PHRASES = (
    "join the team",
    "join our team",
    "work with us",
    "open positions",
    "open roles",
    "we re hiring",
    "we are hiring",
    "trabaja con nosotros",
    "unete al equipo",
)
# Phrases in the page's visible text.
HIRING_TEXT_PHRASES = (
    "we re hiring",
    "we are hiring",
    "now hiring",
    "join our team",
    "estamos contratando",
    "buscamos talento",
)
# Local part of an email address used for hiring: jobs@acme.com.
HIRING_EMAIL_LOCAL_PARTS = frozenset(
    {"careers", "hiring", "jobs", "recruiting", "talent", "empleo", "rrhh"}
)
# Words a fallback page must contain to count (normalized).
HIRING_PAGE_KEYWORDS = (
    "careers",
    "open positions",
    "open roles",
    "openings",
    "we re hiring",
    "we are hiring",
    "join our team",
    "join the team",
    "vacantes",
    "empleo",
    "trabaja con nosotros",
    "posiciones abiertas",
)

# Platforms where only the jobs section is a signal (a company page alone is not).
JOB_SECTION_DOMAINS = frozenset({"linkedin.com", "wellfound.com", "ycombinator.com"})
JOB_SECTION_PATH_PATTERN = re.compile(r"/jobs(/|$)")

NON_VISIBLE_HTML_TAGS = ("script", "style", "noscript", "template", "svg")
MAILTO_SCHEME = "mailto:"
