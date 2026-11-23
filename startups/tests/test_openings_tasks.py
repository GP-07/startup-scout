from datetime import timedelta
from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command
from django.utils import timezone

from sources.constants import SourceKey
from sources.models import Source, SourceRecord
from startups import tasks
from startups.constants import (
    OPENINGS_RECHECK_DAYS,
    InspectionStatus,
    OpeningsStatus,
    StartupStatus,
)
from startups.models import Startup, WebsiteInspection
from startups.openings import startups_due_for_openings_recheck, startups_to_verify

pytestmark = pytest.mark.django_db


def create_startup(
    name, openings_status=OpeningsStatus.NOT_CHECKED, checked_days_ago=None, **fields
):
    startup = Startup.objects.create(name=name, **fields)
    WebsiteInspection.objects.create(
        startup=startup,
        status=InspectionStatus.DONE,
        has_hiring_signal=True,
        hiring_signal_url=f"https://{name.lower()}.com/careers",
        openings_status=openings_status,
        openings_checked_at=(
            timezone.now() - timedelta(days=checked_days_ago)
            if checked_days_ago is not None
            else None
        ),
    )
    return startup


def names(startups):
    return sorted(startup.name for startup in startups)


def test_checked_openings_are_due_again_after_a_week():
    create_startup("Stale", OpeningsStatus.ACTIVE, checked_days_ago=OPENINGS_RECHECK_DAYS + 1)
    create_startup("Fresh", OpeningsStatus.NONE, checked_days_ago=1)
    create_startup("Never", OpeningsStatus.NOT_CHECKED)
    create_startup(
        "Discarded",
        OpeningsStatus.ACTIVE,
        checked_days_ago=OPENINGS_RECHECK_DAYS + 1,
        status=StartupStatus.DISCARDED,
    )

    assert names(startups_due_for_openings_recheck()) == ["Stale"]


def test_recheck_task_verifies_the_due_startups():
    create_startup("Stale", OpeningsStatus.UNVERIFIED, checked_days_ago=OPENINGS_RECHECK_DAYS + 3)

    with mock.patch.object(tasks, "OpeningsVerifier") as verifier_class:
        tasks.recheck_openings_task.call_local()

    [call] = verifier_class.return_value.verify.call_args_list
    assert call.args[0].name == "Stale"


def test_startups_to_verify_are_those_with_a_signal_or_a_job_post():
    create_startup("Signal")
    no_signal = Startup.objects.create(name="Post only")
    SourceRecord.objects.create(
        source=Source.objects.get(key=SourceKey.HACKER_NEWS_HIRING),
        startup=no_signal,
        external_id="post-1",
    )
    Startup.objects.create(name="Nothing")
    create_startup("Checked", OpeningsStatus.ACTIVE, checked_days_ago=1)

    assert names(startups_to_verify()) == ["Post only", "Signal"]
    assert names(startups_to_verify(include_checked=True)) == ["Checked", "Post only", "Signal"]


def test_verify_openings_command_reports_the_statuses():
    create_startup("Signal")
    output = StringIO()

    with mock.patch(
        "startups.management.commands.verify_openings.OpeningsVerifier"
    ) as verifier_class:
        verifier_class.return_value.verify.return_value = mock.Mock(
            openings_status=OpeningsStatus.ACTIVE
        )
        call_command("verify_openings", stdout=output)

    assert "active: 1" in output.getvalue()
