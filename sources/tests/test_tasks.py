from unittest import mock

import pytest

from sources import tasks
from sources.constants import SourceKey
from sources.models import Source

pytestmark = pytest.mark.django_db


def test_daily_task_runs_only_enabled_periodic_sources():
    with mock.patch.object(tasks, "run_source_task") as run_source_task:
        tasks.run_enabled_sources_task.call_local()

    scheduled_source_ids = [call.args[0] for call in run_source_task.call_args_list]
    assert scheduled_source_ids == [Source.objects.get(key=SourceKey.HACKER_NEWS).id]


def test_run_source_task_runs_the_source_with_the_runner():
    source = Source.objects.get(key=SourceKey.HACKER_NEWS)

    with mock.patch.object(tasks, "SourceRunner") as runner_class:
        tasks.run_source_task.call_local(source.id)

    runner_class.return_value.run.assert_called_once_with(source)
