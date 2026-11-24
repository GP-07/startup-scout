from pathlib import Path

import markdown as markdown_library
import nh3
from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static
from django.utils import timezone
from django.utils.safestring import mark_safe

from startups import locations
from web.constants import (
    HOURS_DECIMAL_SEPARATOR,
    HTMX_SCRIPT_URL,
    MARKDOWN_EXTENSIONS,
    MINUS_SIGN,
    OPENINGS_PER_ROW,
    STATIC_VERSION_PARAMETER,
)

register = template.Library()


@register.filter
def markdown(text):
    """Render an analysis body. Raw HTML in it is sanitized away (scripts, handlers...)."""
    rendered_html = markdown_library.markdown(text or "", extensions=MARKDOWN_EXTENSIONS)
    return mark_safe(nh3.clean(rendered_html))  # noqa: S308 - sanitized by nh3 just above


@register.filter
def source_names(startup):
    """Names of the sources that reported the startup, once each (records are prefetched)."""
    names = {record.source.name for record in startup.source_records.all()}
    return ", ".join(sorted(names))


@register.filter
def first_openings(startup):
    """The first active openings of a listed startup (prefetched as `openings`)."""
    return startup.openings[:OPENINGS_PER_ROW]


@register.filter
def hours_from_madrid(timezone_name):
    """The zone's difference from Madrid today: "0 h", "−6 h", "+4,5 h"; blank if unknown."""
    hours = locations.hours_from_reference(timezone_name, timezone.now())
    if hours is None:
        return ""
    number = f"{abs(hours):g}".replace(".", HOURS_DECIMAL_SEPARATOR)
    sign = "" if hours == 0 else ("+" if hours > 0 else MINUS_SIGN)
    return f"{sign}{number} h"


@register.filter
def is_near_madrid(timezone_name):
    return locations.is_near_reference(timezone_name, timezone.now())


@register.filter
def country_name(code):
    return locations.country_name(code)


@register.simple_tag
def versioned_static(path):
    """The static file's URL with its modification time, so browsers never keep an old copy."""
    url = static(path)
    file_path = finders.find(path)
    if not file_path:
        return url
    return f"{url}?{STATIC_VERSION_PARAMETER}={int(Path(file_path).stat().st_mtime)}"


@register.simple_tag
def htmx_script_url():
    return HTMX_SCRIPT_URL
