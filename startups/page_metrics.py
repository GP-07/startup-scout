"""Measures how much a page shows without running JavaScript.

A single-page app often serves an empty shell (`<div id="root"></div>`) and builds its menu and
footer in the browser, where a careers link would be. These numbers make it possible to count
how many inspections without a hiring signal may be such shells, before deciding whether to
render pages with a headless browser.
"""

from dataclasses import dataclass

from bs4 import BeautifulSoup

from startups.constants import (
    APP_ROOT_ELEMENT_IDS,
    SPA_SHELL_MAX_TEXT_LENGTH,
    SPA_SHELL_MIN_LINK_COUNT,
)
from startups.hiring_signal import visible_text


@dataclass(frozen=True)
class PageMetrics:
    text_length: int
    link_count: int
    has_app_root: bool


def measure_page(html):
    soup = BeautifulSoup(html, "html.parser")
    return PageMetrics(
        text_length=len(visible_text(html)),
        link_count=len(soup.find_all("a", href=True)),
        has_app_root=soup.find(id=APP_ROOT_ELEMENT_IDS) is not None,
    )


def is_probable_spa_shell(metrics):
    """Almost no visible text, or a framework mount point with almost no links around it."""
    if metrics.text_length < SPA_SHELL_MAX_TEXT_LENGTH:
        return True
    return metrics.has_app_root and metrics.link_count < SPA_SHELL_MIN_LINK_COUNT
