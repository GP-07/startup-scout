from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command

from startups.constants import InspectionStatus
from startups.inspection_stats import spa_shell_stats
from startups.models import Startup, WebsiteInspection

pytestmark = pytest.mark.django_db


def create_inspection(name, has_hiring_signal=False, status=InspectionStatus.DONE, **metrics):
    startup = Startup.objects.create(name=name, website=f"https://{name.lower()}.com")
    return WebsiteInspection.objects.create(
        startup=startup, status=status, has_hiring_signal=has_hiring_signal, **metrics
    )


SHELL_METRICS = {"home_text_length": 0, "home_link_count": 0, "home_has_app_root": True}
CONTENT_METRICS = {"home_text_length": 900, "home_link_count": 25, "home_has_app_root": False}


def test_counts_probable_shells_among_inspections_without_signal():
    create_inspection("Shell", **SHELL_METRICS)
    create_inspection("Content", **CONTENT_METRICS)
    create_inspection("Legacy")
    create_inspection("Hiring", has_hiring_signal=True, **SHELL_METRICS)
    create_inspection("Failed", status=InspectionStatus.FAILED)

    stats = spa_shell_stats()

    assert stats.without_signal == 3
    assert stats.without_metrics == 1
    assert [inspection.startup.name for inspection in stats.probable_shells] == ["Shell"]


def test_stats_command_lists_probable_shells_without_inspecting():
    create_inspection("Shell", **SHELL_METRICS)
    output = StringIO()

    with mock.patch("startups.management.commands.inspect_websites.WebsiteInspectionService") as (
        service_class
    ):
        call_command("inspect_websites", "--stats", stdout=output)

    service_class.assert_not_called()
    assert "Shell -> https://shell.com" in output.getvalue()
    assert "probable single-page-app shells: 1" in output.getvalue()
