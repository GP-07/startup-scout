"""Figures about past website inspections, to decide on improvements with data."""

from dataclasses import dataclass

from startups.constants import InspectionStatus
from startups.models import WebsiteInspection
from startups.page_metrics import PageMetrics, is_probable_spa_shell


@dataclass(frozen=True)
class SpaShellStats:
    without_signal: int
    without_metrics: int
    probable_shells: list


def spa_shell_stats():
    """Inspections without hiring signal whose home looks like an empty single-page-app shell.

    Inspections stored before the home metrics existed have none: `inspect_websites --all`
    measures them again.
    """
    without_signal = WebsiteInspection.objects.filter(
        status=InspectionStatus.DONE, has_hiring_signal=False
    ).select_related("startup")
    measured = [inspection for inspection in without_signal if _is_measured(inspection)]
    return SpaShellStats(
        without_signal=len(without_signal),
        without_metrics=len(without_signal) - len(measured),
        probable_shells=[
            inspection for inspection in measured if is_probable_spa_shell(_metrics_of(inspection))
        ],
    )


def _is_measured(inspection):
    return inspection.home_text_length is not None


def _metrics_of(inspection):
    return PageMetrics(
        text_length=inspection.home_text_length,
        link_count=inspection.home_link_count,
        has_app_root=inspection.home_has_app_root,
    )
