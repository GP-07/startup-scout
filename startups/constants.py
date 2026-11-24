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


# Marking an analysis as sent moves the startup to `contacted`, unless it is already there or later.
STATUSES_AFTER_CONTACT = (StartupStatus.CONTACTED, StartupStatus.REPLIED)
ANALYSIS_SENT_NOTE = "Análisis enviado: {title}"


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


# People who decide: the "contact" filter of the startup list looks for these first.
PERSON_CONTACT_ROLES = (ContactRole.CEO, ContactRole.CTO, ContactRole.FOUNDER)
# Contacts worth writing to: a person who decides or a general mailbox.
KEY_CONTACT_ROLES = (
    ContactRole.CEO,
    ContactRole.CTO,
    ContactRole.FOUNDER,
    ContactRole.GENERAL,
)

# When the same person is found twice with different roles, the first of these wins.
CONTACT_ROLE_STRENGTH = (
    ContactRole.CEO,
    ContactRole.CTO,
    ContactRole.FOUNDER,
    ContactRole.OTHER,
    ContactRole.GENERAL,
)


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

# Shortest company name prefix compared with a domain label ("acme" in `acmehq.com`).
COMPANY_NAME_MATCH_MIN_LENGTH = 3

# Contacts found on the startup's own website (docs/startup-scout-design.md §5).
# Pages besides the home where startups introduce their team or how to reach them.
CONTACT_PAGE_SLUGS = frozenset(
    {
        "about",
        "about-us",
        "company",
        "contact",
        "contact-us",
        "contacto",
        "equipo",
        "founders",
        "nosotros",
        "our-team",
        "people",
        "quienes-somos",
        "sobre-nosotros",
        "team",
        "the-team",
    }
)
# Tried when the home links to none of the pages above, in this order.
CONTACT_FALLBACK_PATHS = (
    "/about",
    "/about-us",
    "/team",
    "/contact",
    "/nosotros",
    "/equipo",
    "/quienes-somos",
    "/contacto",
)
# Pages visited for contacts besides the home (all the fallback paths fit).
CONTACT_MAX_EXTRA_PAGES = 8
# Mailboxes of the company rather than of a person.
GENERAL_EMAIL_LOCAL_PARTS = frozenset(
    {
        "contact",
        "contacto",
        "founders",
        "hello",
        "hey",
        "hi",
        "hola",
        "info",
        "office",
        "partners",
        "press",
        "sales",
        "support",
        "team",
    }
)
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
LINKEDIN_DOMAIN = "linkedin.com"
LINKEDIN_PROFILE_PATH_PREFIX = "/in/"
JSON_LD_SCRIPT_TYPE = "application/ld+json"
JSON_LD_PERSON_TYPE = "Person"
JSON_LD_FOUNDER_KEY = "founder"
# Only people listed as the organization's own count: not review authors or quoted customers.
JSON_LD_TEAM_KEYS = frozenset(
    {"", "@graph", "employee", "employees", "founder", "founders", "member", "members"}
)
JSON_LD_WORKS_FOR_KEY = "worksFor"
# Sections whose people are not the startup's team (normalized heading phrases).
NON_TEAM_SECTION_PHRASES = (
    "advisor",
    "advisors",
    "angels",
    "backed by",
    "backers",
    "customers",
    "investors",
    "loved by",
    "testimonials",
    "trusted by",
    "what people say",
)
SECTION_HEADING_TAGS = ("h1", "h2", "h3", "h4")
# How many headings back to look for the section a person is in (card names are headings too).
SECTION_HEADING_LOOKBEHIND = 3
# A fragment like this after a job title introduces the company: "Co-founder" "at" "Globex".
JOB_TITLE_COMPANY_MARKERS = frozenset({"at", "@", "of", "en", "de"})
# Normalized phrases (see hiring_signal.normalize_text) that give a person's role.
# Checked in this order: "CEO & Co-founder" is a CEO.
ROLE_TITLE_PHRASES = (
    (ContactRole.CEO, ("ceo", "chief executive")),
    (ContactRole.CTO, ("cto", "chief technology", "chief technical")),
    (
        ContactRole.FOUNDER,
        (
            "founder",
            "cofounder",
            "fundador",
            "fundadora",
            "cofundador",
            "cofundadora",
        ),
    ),
)
# What follows these in a job title is a company: "CEO at Globex", "CTO of Initech", "Founder, X".
# If it is not the startup itself, the person is a customer quoted in a testimonial.
JOB_TITLE_COMPANY_MARKER_PATTERN = re.compile(
    r"\s+(?:at|of|@|en|de)\s+|\s*,\s*|\s+@", re.IGNORECASE
)
# A line with a role is a job title only if it is this short (longer lines are prose).
ROLE_LINE_MAX_WORDS = 8
# How many text fragments back from a job title to look for the person's name (team cards).
NAME_LOOKBEHIND_FRAGMENTS = 3
PERSON_NAME_MIN_WORDS = 2
PERSON_NAME_MAX_WORDS = 4
PERSON_NAME_MAX_LENGTH = 50
# Separators between a name and a job title on one line: "Jane Roe, Founder".
NAME_ROLE_SEPARATOR_PATTERN = re.compile(r"\s*(?:,|\||:|\s[-–—]\s)\s*")
PERSON_NAME_WORD_PATTERN = re.compile(r"^[^\W\d_][^\W\d_'’.-]*(?:['’.-][^\W\d_]+)*\.?$")
# Capitalized words that start headings and links, not names: "Our Team", "Meet Jane".
NOT_NAME_WORDS = frozenset(
    {
        "about",
        "advisory",
        "built",
        "business",
        "by",
        "chief",
        "contact",
        "council",
        "counsel",
        "custom",
        "customer",
        "director",
        "engineer",
        "free",
        "general",
        "grade",
        "head",
        "i’m",
        "i'm",
        "lead",
        "los",
        "manager",
        "motion",
        "new",
        "officer",
        "quotes",
        "san",
        "start",
        "founders",
        "home",
        "join",
        "linkedin",
        "meet",
        "our",
        "team",
        "the",
        "us",
        "with",
    }
)


# Open positions actually published today (docs/startup-scout-design.md §3).
class OpeningsStatus(models.TextChoices):
    NOT_CHECKED = "not_checked", "Sin señal"
    ACTIVE = "active", "Búsquedas activas"
    NONE = "none", "Sin búsquedas activas"
    UNVERIFIED = "unverified", "Sin verificar"


class OpeningOrigin(models.TextChoices):
    ASHBY = "ashby", "Ashby"
    GREENHOUSE = "greenhouse", "Greenhouse"
    LEVER = "lever", "Lever"
    WEBSITE = "website", "Web de la startup"


class JobBoardProvider(models.TextChoices):
    """Job boards whose official public API lists a company's openings with their dates."""

    ASHBY = "ashby", "Ashby"
    GREENHOUSE = "greenhouse", "Greenhouse"
    LEVER = "lever", "Lever"


# An opening with a publication date counts while it is this recent. Openings listed on the
# startup's own page usually have no date: those count while they are published.
OPENINGS_MAX_AGE_DAYS = 60
# Openings change: they are checked again once they are this old, a batch per hourly run.
OPENINGS_RECHECK_DAYS = 7
OPENINGS_RECHECK_BATCH = 50
OPENINGS_RECHECK_MINUTE = 30
OPENINGS_RECHECK_LOCK = "openings-recheck"
WEB_URL_SCHEMES = frozenset({"http", "https"})
# Cloudflare replaces email addresses with links to this path: not a page to read.
EMAIL_PROTECTION_PATH = "/cdn-cgi/l/email-protection"
# A careers page often only links to where the jobs are ("See open positions").
OPEN_POSITIONS_LINK_PHRASES = (
    "all jobs",
    "current openings",
    "explore our open positions",
    "job openings",
    "open positions",
    "open roles",
    "see jobs",
    "view jobs",
    "view open roles",
    "view openings",
    "posiciones abiertas",
    "busquedas abiertas",
    "ver vacantes",
)
OPEN_POSITIONS_LINKS_FOLLOWED = 2

ASHBY_API_URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}"
ASHBY_BOARD_URL = "https://jobs.ashbyhq.com/{slug}"
GREENHOUSE_API_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
# `content` adds each job's description, to read the languages it requires.
GREENHOUSE_API_PARAMS = {"content": "true"}
GREENHOUSE_BOARD_URL = "https://job-boards.greenhouse.io/{slug}"
# Lever hosts some accounts in the EU: a 404 on the first host is retried on the second.
LEVER_API_URLS = (
    "https://api.lever.co/v0/postings/{slug}",
    "https://api.eu.lever.co/v0/postings/{slug}",
)
LEVER_API_PARAMS = {"mode": "json"}
LEVER_BOARD_URL = "https://jobs.lever.co/{slug}"
LEVER_REMOTE_WORKPLACE = "remote"
LEVER_ONSITE_WORKPLACES = frozenset({"onsite", "on-site", "hybrid"})
MILLISECONDS_PER_SECOND = 1000
# Where each job board appears in a page or a link, with the company's board slug captured.
JOB_BOARD_PATTERNS = (
    (JobBoardProvider.ASHBY, re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9][\w.%-]*)")),
    (
        JobBoardProvider.GREENHOUSE,
        re.compile(
            r"(?:job-)?boards(?:\.eu)?\.greenhouse\.io/(?:embed/job_board(?:/js)?\?for=)?([\w-]+)"
        ),
    ),
    (JobBoardProvider.LEVER, re.compile(r"jobs(?:\.eu)?\.lever\.co/([\w.-]+)")),
)
JOB_BOARD_RESERVED_SLUGS = frozenset({"api", "embed", "js", "v1"})
# `jobs.ashbyhq.com/acme/<job id>` is a job's page; `jobs.ashbyhq.com/acme` is the whole board.
JOB_BOARD_JOB_PAGE_MIN_SEGMENTS = 2
JOB_BOARD_URLS = {
    JobBoardProvider.ASHBY: ASHBY_BOARD_URL,
    JobBoardProvider.GREENHOUSE: GREENHOUSE_BOARD_URL,
    JobBoardProvider.LEVER: LEVER_BOARD_URL,
}
# A link on a careers page is an opening when it goes to a job page and its text names a job.
JOB_PAGE_PATH_PATTERN = re.compile(
    r"/(?:careers?|jobs?|positions?|openings?|roles?|vacanc(?:y|ies)|empleos?|vacantes?|join-us)"
    r"/[^/]+/?$"
)
JOB_TITLE_WORDS = (
    "account executive",
    "analyst",
    "architect",
    "designer",
    "desarrollador",
    "desarrolladora",
    "developer",
    "director",
    "disenador",
    "disenadora",
    "engineer",
    "head",
    "ingeniera",
    "ingeniero",
    "intern",
    "lead",
    "manager",
    "marketing",
    "operations",
    "programador",
    "recruiter",
    "researcher",
    "sales",
    "scientist",
    "specialist",
    "success",
    "support",
    "writer",
)
JOB_TITLE_MAX_LENGTH = 200
JOB_LOCATION_MAX_LENGTH = 200
JOB_DESCRIPTION_MAX_LENGTH = 50_000
LEVER_DESCRIPTION_FIELDS = ("descriptionPlain", "additionalPlain")
JOB_TITLE_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6", "strong")
# Normalized phrases of applications that are not an opening (a pool of candidates).
GENERIC_APPLICATION_PHRASES = (
    "candidatura abierta",
    "candidatura espontanea",
    "don t see",
    "dont see",
    "future opportunities",
    "general application",
    "open application",
    "spontaneous application",
    "talent pool",
    "unsolicited application",
)
# Normalized phrases of a careers page without openings.
NO_OPENINGS_PHRASES = (
    "no current openings",
    "no hay busquedas abiertas",
    "no hay posiciones abiertas",
    "no hay vacantes",
    "no job openings",
    "no open positions",
    "no open roles",
    "no openings",
    "no positions available",
    "no tenemos posiciones abiertas",
    "no vacancies",
    "not currently hiring",
    "not hiring right now",
)
REMOTE_WORDS = ("remote", "remoto", "remota", "anywhere", "telecommute")
JSON_LD_JOB_POSTING_TYPE = "JobPosting"
JSON_LD_REMOTE_LOCATION_TYPE = "TELECOMMUTE"


# Where a startup is established, to filter by time difference (docs/startup-scout-design.md §3).
class LocationSource(models.TextChoices):
    """Where the headquarters country comes from, by decreasing priority."""

    MANUAL = "manual", "Corregido a mano"
    WEBSITE_ADDRESS = "website_address", "Dirección en su web"
    HEADQUARTERS = "headquarters", "Sede declarada"
    WORKPLACES = "workplaces", "Lugares de sus puestos"
    COUNTRY_DOMAIN = "country_domain", "Dominio de país"
    # Openings only "Remote" or in regions ("EMEA"): no country, counted as near Madrid unless
    # every region named is far (decision of 2026-11-23).
    REMOTE = "remote", "Remoto o regiones, sin país"


# Time differences are measured against this zone, with daylight saving time on both sides.
REFERENCE_TIMEZONE = "Europe/Madrid"
MAX_HOURS_FROM_REFERENCE = 5
SECONDS_PER_HOUR = 3600
LOCATION_EVIDENCE_MAX_LENGTH = 500
LOCATION_EVIDENCE_SEPARATOR = "; "
STARTUP_LOCATION_FIELDS = (
    "hq_country",
    "hq_city",
    "hq_timezone",
    "location_source",
    "location_evidence",
    "location_detected_at",
)
# A location text is split into places at these separators; a place's parts at commas
# ("Vienna, VA, USA": city, state, country).
LOCATION_SEPARATORS_PATTERN = re.compile(
    r"[;|/()\[\]{}+&·•:\n]|\s[-–—]\s|\bor\b|\band\b|\bo\b|\by\b", re.IGNORECASE
)
LOCATION_PART_SEPARATOR = ","
# Words around a place that are not part of its name ("San Francisco Office", "Remote (EU)").
LOCATION_NOISE_WORDS = frozenset(
    {
        "almost",
        "anywhere",
        "area",
        "based",
        "city",
        "distributed",
        "fully",
        "global",
        "greater",
        "headquarters",
        "hours",
        "hq",
        "hybrid",
        "in",
        "metro",
        "office",
        "offices",
        "on-site",
        "onsite",
        "only",
        "overlap",
        "preferred",
        "remote",
        "remote-first",
        "surroundings",
        "time",
        "timezone",
        "timezones",
        "worldwide",
        "zone",
        "zones",
    }
)
# Words that are never a place, though a small town carries them as a name or alias.
NOT_A_PLACE_WORDS = frozenset(
    {"central", "contract", "field", "north", "rust", "south", "east", "west", "time"}
)
# Places named in a location text that declare the headquarters ("San Leandro HQ").
HEADQUARTERS_WORDS = ("hq", "headquarters", "head office", "sede central")
# Country names besides GeoNames' own.
COUNTRY_ALIASES = {
    "america": "US",
    "britain": "GB",
    "czech republic": "CZ",
    "england": "GB",
    "great britain": "GB",
    "holland": "NL",
    "korea": "KR",
    "northern ireland": "GB",
    "scotland": "GB",
    "the netherlands": "NL",
    "turkiye": "TR",
    "uae": "AE",
    "uk": "GB",
    "united states of america": "US",
    "us": "US",
    "usa": "US",
    "wales": "GB",
}
# Cities known by a short name, as GeoNames calls them.
CITY_ALIASES = {
    "kiev": "kyiv",
    "new york": "new york city",
    "nyc": "new york city",
    "san francisco bay": "san francisco",
    "sf": "san francisco",
    "sf bay": "san francisco",
    "silicon valley": "san jose",
    "washington dc": "washington",
}
# Regions and time zones: a zone without a country.
REGION_TIMEZONES = {
    "cest": "Europe/Paris",
    "cet": "Europe/Paris",
    "central european": "Europe/Paris",
    "eastern": "America/New_York",
    "emea": "Europe/Paris",
    "est": "America/New_York",
    "et": "America/New_York",
    "eea": "Europe/Paris",
    "eu": "Europe/Paris",
    "europe": "Europe/Paris",
    "european union": "Europe/Paris",
    "gmt": "Europe/London",
    "latam": "America/Sao_Paulo",
    "latin america": "America/Sao_Paulo",
    "north america": "America/Chicago",
    "pacific": "America/Los_Angeles",
    "pst": "America/Los_Angeles",
    "pt": "America/Los_Angeles",
    "utc": "Etc/UTC",
}
# "UTC+1", "GMT-5": `Etc/GMT` zones have the opposite sign.
UTC_OFFSET_PATTERN = re.compile(r"\b(?:utc|gmt)\s*([+-])\s*(\d{1,2})\b", re.IGNORECASE)
UTC_OFFSET_TIMEZONE = "Etc/GMT{sign}{hours}"
US_STATE_CODE_LENGTH = 2
US_STATE_ALIASES = {"dc": "DC", "washington dc": "DC"}


class LocationPartKind(models.TextChoices):
    """What a part of a location text names."""

    REGION = "region"
    COUNTRY = "country"
    STATE = "state"
    CITY = "city"


# A "Who is hiring?" post starts with a header line: "Company | Role | Place | ONSITE".
HIRING_POST_HEADER_END_PATTERN = re.compile(r"<p>|\n", re.IGNORECASE)
HIRING_POST_HEADER_SEPARATOR = "|"
HIRING_POST_NOT_A_PLACE_MARKS = ("http", "$", "£", "€", "@")
# Header segments naming roles, not places ("Software Engineers (backend, mobile)").
HIRING_POST_ROLE_WORDS = frozenset(
    {"ceo", "coo", "cto", "engineering", "founder", "founding", "hiring", "role", "roles"}
)
# Alternate city names shorter than this are too often common words or abbreviations.
CITY_ALTERNATE_NAME_MIN_LENGTH = 5
US_COUNTRY_CODE = "US"
# Country-code domains that many startups use with no tie to the country.
GENERIC_COUNTRY_DOMAINS = frozenset(
    {
        "ai",
        "app",
        "cc",
        "co",
        "cx",
        "fm",
        "gg",
        "io",
        "is",
        "ly",
        "me",
        "sh",
        "so",
        "to",
        "tv",
        "ws",
    }
)
COUNTRY_DOMAIN_ALIASES = {"uk": "GB"}
COUNTRY_CODE_LENGTH = 2
GREENHOUSE_OFFICES_API_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/offices"
ORGANIZATION_ADDRESS_FIELDS = ("addressLocality", "addressRegion", "addressCountry")
# schema.org types whose `address` is the company's.
JSON_LD_ORGANIZATION_TYPES = frozenset(
    {"Corporation", "LocalBusiness", "Organization", "ProfessionalService"}
)


# Technical openings: software roles, to keep only startups that hire for them
# (docs/startup-scout-design.md §3). Normalized phrases (startups/hiring_signal.normalize_text).
# A software word makes the title technical by itself ("Software Engineer, Solutions").
SOFTWARE_ROLE_PHRASES = (
    "back end",
    "backend",
    "cto",
    "desarrollador",
    "desarrolladora",
    "developer",
    "front end",
    "frontend",
    "full stack",
    "fullstack",
    "programador",
    "programadora",
    "programmer",
    "software",
    "tech lead",
)
# Specialties left out even with a software word (decision of 2026-11-24): data analytics,
# forward deployed, security, infrastructure and platforms, developer relations, machine
# learning and research, DevOps, QA, internships and graduates, founding roles, directors and
# heads, and a few others seen (MBSE, robotics integration, product design, strike, compliance
# engineers); and design or documentation roles that carry "Developer". Engineering managers
# do count.
EXCLUDED_TECHNICAL_SPECIALTY_PHRASES = (
    "analytics",
    "applied scientist",
    "baremetal",
    "cloud operations",
    "compliance engineer",
    "computer vision",
    "cybersecurity",
    "data center",
    "data engineer",
    "data engineering",
    "data pipeline",
    "data pipelines",
    "data platform",
    "data warehouse",
    "data warehousing",
    "data science",
    "data scientist",
    "datacenters",
    "deep learning",
    "deployed",
    "designer",
    "developer advocate",
    "developer relations",
    "developer success",
    "devops",
    "devrel",
    "devsecops",
    "director",
    "documentation",
    "engineering expert",
    "etl",
    "founding",
    "gpu",
    "graduate",
    "graduates",
    "head of",
    "inference",
    "infra",
    "infosec",
    "infrastructure",
    "intern",
    "interns",
    "internship",
    "internships",
    "machine learning",
    "mbse",
    "ml",
    "mlops",
    "new grad",
    "new graduate",
    "new grads",
    "networking",
    "observability",
    "pasante",
    "pasantia",
    "platform engineer",
    "practica",
    "practicas",
    "product design",
    "production engineer",
    "qa",
    "quality assurance",
    "research",
    "researcher",
    "robotics integration",
    "sdet",
    "security",
    "site reliability",
    "sre",
    "strike",
    "test automation",
    "tester",
    "testing",
)
# Frontend only, which I am not a specialist in: discarded unless the title also says full stack.
FRONTEND_ROLE_PHRASES = (
    "angular",
    "front end",
    "frontend",
    "next js",
    "nextjs",
    "react",
    "svelte",
    "ui developer",
    "ui engineer",
    "vue",
)
FULL_STACK_ROLE_PHRASES = ("full stack", "fullstack")
# Generic engineering words: technical unless the title names another discipline.
ENGINEERING_ROLE_PHRASES = (
    "architect",
    "engineer",
    "engineering",
    "ingeniera",
    "ingeniero",
)
# Disciplines whose engineers do not build software, or roles that only carry the word.
NON_SOFTWARE_ENGINEERING_PHRASES = (
    "criticality",
    "customer success",
    "electrical",
    "enablement",
    "gtm",
    "hydraulics",
    "legal",
    "manufacturing",
    "mechanical",
    "mechatronics",
    "nuclear",
    "process",
    "recruiter",
    "safety",
    "sales",
    "solar",
    "solution engineer",
    "solutions engineer",
    "thermal",
)


# Languages an opening may require besides English and Spanish (decision of 2026-11-24): the
# name shown, then its normalized names (English and its own).
OTHER_LANGUAGES = (
    ("Arabic", ("arabic",)),
    ("Catalan", ("catalan", "catala")),
    ("Chinese", ("chinese", "mandarin", "cantonese")),
    ("Czech", ("czech",)),
    ("Danish", ("danish", "dansk")),
    ("Dutch", ("dutch", "nederlands")),
    ("Finnish", ("finnish", "suomi")),
    ("French", ("french", "francais")),
    ("German", ("german", "deutsch")),
    ("Greek", ("greek",)),
    ("Hebrew", ("hebrew",)),
    ("Hindi", ("hindi",)),
    ("Hungarian", ("hungarian",)),
    ("Indonesian", ("indonesian", "bahasa")),
    ("Italian", ("italian", "italiano")),
    ("Japanese", ("japanese",)),
    ("Korean", ("korean",)),
    ("Norwegian", ("norwegian", "norsk")),
    ("Polish", ("polish", "polski")),
    ("Portuguese", ("portuguese", "portugues")),
    ("Romanian", ("romanian",)),
    ("Russian", ("russian",)),
    ("Swedish", ("swedish", "svenska")),
    ("Thai", ("thai",)),
    ("Turkish", ("turkish",)),
    ("Ukrainian", ("ukrainian",)),
    ("Vietnamese", ("vietnamese",)),
)
# In a title, this word asks for several languages.
MULTILINGUAL_LANGUAGE = "Multilingual"
MULTILINGUAL_WORDS = ("multilingual",)
# Words that make a sentence naming a language a requirement ("Fluent in German").
LANGUAGE_REQUIREMENT_WORDS = (
    "b2",
    "bilingual",
    "c1",
    "c2",
    "fliessend",
    "fluency",
    "fluent",
    "fluently",
    "kenntnisse",
    "language skills",
    "mother tongue",
    "native",
    "proficiency",
    "proficient",
    "speak",
    "speaker",
    "speakers",
    "speaking",
    "spoken",
    "written and spoken",
    "written and verbal",
)
# Compound words that require a language by themselves.
LANGUAGE_REQUIREMENT_COMPOUNDS = {"deutschkenntnisse": "German", "franzosischkenntnisse": "French"}
# Words that make it optional ("German is a plus").
OPTIONAL_LANGUAGE_WORDS = (
    "advantage",
    "asset",
    "beneficial",
    "bonus",
    "ideally",
    "nice to have",
    "plus",
    "preferred",
    "wunschenswert",
)
# A description is read sentence by sentence: a requirement names the language in its sentence.
DESCRIPTION_BLOCK_TAGS = ("br", "div", "h1", "h2", "h3", "h4", "li", "p", "tr")
DESCRIPTION_SENTENCE_SEPARATORS = re.compile(r"[.!?;•\n]+")


# Countries where I cannot work without a visa (Italian citizen, resident in Spain): an opening
# only there is discarded (decision of 2026-11-24).
COUNTRIES_REQUIRING_WORK_AUTHORIZATION = frozenset({"GB"})
# Countries where an Italian citizen works without a visa: the EU, the EEA and Switzerland. An
# opening only elsewhere is discarded when its description says it sponsors no visa.
COUNTRIES_WITHOUT_WORK_AUTHORIZATION = frozenset(
    {
        "AT",
        "BE",
        "BG",
        "CH",
        "CY",
        "CZ",
        "DE",
        "DK",
        "EE",
        "ES",
        "FI",
        "FR",
        "GR",
        "HR",
        "HU",
        "IE",
        "IS",
        "IT",
        "LI",
        "LT",
        "LU",
        "LV",
        "MT",
        "NL",
        "NO",
        "PL",
        "PT",
        "RO",
        "SE",
        "SI",
        "SK",
    }
)
# A sentence about visas or work authorization...
SPONSORSHIP_WORDS = ("sponsor", "sponsorship", "sponsorships", "visa", "visas")
# ...that refuses it ("We are unable to provide visa sponsorship", "Not available for this role").
SPONSORSHIP_REFUSAL_WORDS = (
    "can t",
    "cannot",
    "do not",
    "does not",
    "don t",
    "no",
    "not",
    "unable",
    "will not",
    "without",
    "won t",
)
# Requirements that leave sponsorship out without naming it.
WORK_AUTHORIZATION_REQUIREMENTS = (
    "legally authorized to work",
    "legally entitled to work",
    "must be authorized to work",
    "must be eligible to work",
    "must have the right to work",
    "work authorization is required",
)
# An opening open from anywhere is not tied to its company's country.
ANYWHERE_WORDS = ("anywhere", "global", "globally", "worldwide")


# Sites that are job boards or aggregators the rules could not tell apart from a startup: their
# startup is discarded with this reason, and a source reporting them again changes nothing.
BLACKLIST_DEFAULT_REASON = "Lista negra: bolsa de trabajo"
