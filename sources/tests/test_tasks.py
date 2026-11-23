from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

import pytest

from sources import tasks
from sources.constants import SourceKey, SourceRunStatus
from sources.models import Source, SourceRun

pytestmark = pytest.mark.django_db


MADRID = ZoneInfo("Europe/Madrid")
MORNING_AFTER_DISCOVERY = datetime(2026, 11, 20, 10, 0, tzinfo=MADRID)


def scheduled_keys(now):
    """Source keys the hourly discovery task schedules when it runs at `now`."""
    with (
        mock.patch.object(tasks, "run_source_task") as run_source_task,
        mock.patch.object(tasks.timezone, "now", return_value=now),
    ):
        tasks.run_enabled_sources_task.call_local()
    scheduled_ids = [call.args[0] for call in run_source_task.call_args_list]
    return set(Source.objects.filter(id__in=scheduled_ids).values_list("key", flat=True))


def record_run(source_key, started_at, status=SourceRunStatus.SUCCEEDED):
    run = SourceRun.objects.create(source=Source.objects.get(key=source_key), status=status)
    SourceRun.objects.filter(pk=run.pk).update(started_at=started_at)


def test_runs_every_enabled_periodic_source_not_yet_run_today():
    assert scheduled_keys(MORNING_AFTER_DISCOVERY) == {
        SourceKey.HACKER_NEWS,
        SourceKey.HACKER_NEWS_HIRING,
    }


def test_nothing_runs_before_the_discovery_hour():
    assert scheduled_keys(datetime(2026, 11, 20, 6, 59, tzinfo=MADRID)) == set()


def test_source_that_already_succeeded_today_is_not_run_again():
    record_run(SourceKey.HACKER_NEWS, datetime(2026, 11, 20, 7, 0, tzinfo=MADRID))

    assert scheduled_keys(MORNING_AFTER_DISCOVERY) == {SourceKey.HACKER_NEWS_HIRING}


@pytest.mark.parametrize(
    ("started_at", "status"),
    [
        # Yesterday's run, or one by hand before today's discovery hour, is not today's.
        (datetime(2026, 11, 19, 9, 0, tzinfo=MADRID), SourceRunStatus.SUCCEEDED),
        (datetime(2026, 11, 20, 6, 0, tzinfo=MADRID), SourceRunStatus.SUCCEEDED),
        # A failed run is retried at the next hourly check.
        (datetime(2026, 11, 20, 7, 0, tzinfo=MADRID), SourceRunStatus.FAILED),
    ],
)
def test_missed_or_failed_discovery_is_caught_up(started_at, status):
    record_run(SourceKey.HACKER_NEWS, started_at, status)

    assert SourceKey.HACKER_NEWS in scheduled_keys(MORNING_AFTER_DISCOVERY)


def test_disabled_sources_are_not_run():
    Source.objects.filter(key=SourceKey.HACKER_NEWS).update(enabled=False)

    assert scheduled_keys(MORNING_AFTER_DISCOVERY) == {SourceKey.HACKER_NEWS_HIRING}


def test_run_source_task_runs_the_source_with_the_runner():
    source = Source.objects.get(key=SourceKey.HACKER_NEWS)

    with mock.patch.object(tasks, "SourceRunner") as runner_class:
        tasks.run_source_task.call_local(source.id)

    runner_class.return_value.run.assert_called_once_with(source)
