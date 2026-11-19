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

# Platforms whose links point to content inside them (a repository, an app store page, a profile):
# their domain says nothing about which startup it is, so it is never used as identity.
NON_IDENTIFYING_DOMAINS = frozenset(
    {
        "apple.com",
        "archive.org",
        "arxiv.org",
        "bitbucket.org",
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
        "sourceforge.net",
        "t.me",
        "tiktok.com",
        "twitter.com",
        "wikipedia.org",
        "x.com",
        "ycombinator.com",
        "youtu.be",
        "youtube.com",
    }
)

# Hosts that give each customer a subdomain but are missing from the Public Suffix List:
# `acme.substack.com` identifies Acme, while `substack.com` alone identifies nobody.
SHARED_HOST_DOMAINS = frozenset(
    {
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
