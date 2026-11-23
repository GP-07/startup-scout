import markdown as markdown_library
import nh3
from django import template
from django.utils.safestring import mark_safe

from web.constants import HTMX_SCRIPT_URL, MARKDOWN_EXTENSIONS, OPENINGS_PER_ROW

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


@register.simple_tag
def htmx_script_url():
    return HTMX_SCRIPT_URL
