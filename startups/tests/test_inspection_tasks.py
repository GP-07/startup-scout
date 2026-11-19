from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command

from sources.constants import SourceKey
from sources.models import Source
from startups import tasks
from startups.constants import InspectionStatus
from startups.ingestion import StartupIngestionService
from startups.models import WebsiteInspection
from startups.tests.fakes import FakeRedirectResolver, build_raw_startup

pytestmark = pytest.mark.django_db


def create_startup(external_id, name, website):
    source = Source.objects.get(key=SourceKey.HACKER_NEWS)
    service = StartupIngestionService(redirect_resolver=FakeRedirectResolver())
    return service.ingest(source, build_raw_startup(external_id, name, website=website)).startup


def test_enqueue_marks_pending_and_schedules_task_for_startups_with_own_domain():
    startup = create_startup("hn-1", "Acme", "https://acme.com")

    with mock.patch.object(tasks, "inspect_website_task") as inspect_website_task:
        tasks.enqueue_website_inspection(startup)

    inspect_website_task.assert_called_once_with(startup.id)
    assert startup.website_inspection.status == InspectionStatus.PENDING


def test_enqueue_skips_startups_without_own_domain():
    startup = create_startup("hn-1", "Tiny dates", "https://github.com/someone/tiny-dates")

    with mock.patch.object(tasks, "inspect_website_task") as inspect_website_task:
        tasks.enqueue_website_inspection(startup)

    inspect_website_task.assert_not_called()
    assert not WebsiteInspection.objects.exists()


def test_inspect_website_task_runs_the_service():
    startup = create_startup("hn-1", "Acme", "https://acme.com")

    with mock.patch.object(tasks, "WebsiteInspectionService") as service_class:
        tasks.inspect_website_task.call_local(startup.id)

    service_class.return_value.inspect.assert_called_once_with(startup)


def test_command_inspects_only_startups_never_inspected_by_default():
    already_inspected = create_startup("hn-1", "Acme", "https://acme.com")
    WebsiteInspection.objects.create(startup=already_inspected, status=InspectionStatus.DONE)
    never_inspected = create_startup("hn-2", "Brisa", "https://brisa.com")
    create_startup("hn-3", "Tiny dates", "https://github.com/someone/tiny-dates")

    with mock.patch(
        "startups.management.commands.inspect_websites.WebsiteInspectionService"
    ) as service_class:
        call_command("inspect_websites", stdout=StringIO())

    inspected = [call.args[0] for call in service_class.return_value.inspect.call_args_list]
    assert inspected == [never_inspected]


def test_command_with_all_flag_inspects_every_startup_with_own_domain():
    acme = create_startup("hn-1", "Acme", "https://acme.com")
    WebsiteInspection.objects.create(startup=acme, status=InspectionStatus.DONE)
    brisa = create_startup("hn-2", "Brisa", "https://brisa.com")

    with mock.patch(
        "startups.management.commands.inspect_websites.WebsiteInspectionService"
    ) as service_class:
        call_command("inspect_websites", "--all", stdout=StringIO())

    inspected = {call.args[0] for call in service_class.return_value.inspect.call_args_list}
    assert inspected == {acme, brisa}
