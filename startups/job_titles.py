"""Tells the software roles I look for apart from the rest, by the title of an opening.

Pure functions: no network and no database. Seniority words alone ("Senior", "Lead", "Staff")
do not make a role technical: "Senior Account Executive" or "Chief of Staff" are not. Some
software specialties are left out too: data analytics, forward deployed, security,
infrastructure, developer relations, machine learning, DevOps, data engineering, and frontend
roles that are not also full stack.
"""

from startups.constants import (
    ENGINEERING_ROLE_PHRASES,
    EXCLUDED_TECHNICAL_SPECIALTY_PHRASES,
    FRONTEND_ROLE_PHRASES,
    FULL_STACK_ROLE_PHRASES,
    NON_SOFTWARE_ENGINEERING_PHRASES,
    SOFTWARE_ROLE_PHRASES,
)
from startups.hiring_signal import normalize_text


def is_technical_title(title):
    """Whether the opening is a software role I look for ("Backend Engineer").

    An excluded specialty settles it first ("Backend Engineer, ML Inference" is not); then a
    software word; then a generic engineering word, unless the title names another discipline
    ("Mechanical Engineer") or a role that only carries the word ("Sales Engineer").
    """
    normalized_title = f" {normalize_text(title or '')} "
    if contains_any(normalized_title, EXCLUDED_TECHNICAL_SPECIALTY_PHRASES):
        return False
    is_frontend = contains_any(normalized_title, FRONTEND_ROLE_PHRASES)
    if is_frontend and not contains_any(normalized_title, FULL_STACK_ROLE_PHRASES):
        return False  # Frontend only.
    if contains_any(normalized_title, SOFTWARE_ROLE_PHRASES):
        return True
    return contains_any(normalized_title, ENGINEERING_ROLE_PHRASES) and not contains_any(
        normalized_title, NON_SOFTWARE_ENGINEERING_PHRASES
    )


def contains_any(padded_text, phrases):
    """Whether a normalized text padded with spaces contains any of the phrases as words."""
    return any(f" {phrase} " in padded_text for phrase in phrases)
