from datetime import timedelta

import pytest
from django.utils import timezone

from sources.constants import SourceKey
from sources.models import Source, SourceRecord
from startups.constants import HIRING_POST_MAX_AGE_DAYS, InspectionStatus
from startups.models import Startup, WebsiteInspection

pytestmark = pytest.mark.django_db


def create_startup(name):
    return Startup.objects.create(name=name)


def add_record(startup, source_key, published_days_ago):
    SourceRecord.objects.create(
        source=Source.objects.get(key=source_key),
        startup=startup,
        external_id=f"{startup.name}-{source_key}-{published_days_ago}",
        published_at=timezone.now() - timedelta(days=published_days_ago),
    )


def add_inspection(startup, has_hiring_signal):
    WebsiteInspection.objects.create(
        startup=startup, status=InspectionStatus.DONE, has_hiring_signal=has_hiring_signal
    )


def hiring_status_of(startup):
    annotated = Startup.objects.with_hiring_signal().get(pk=startup.pk)
    return (
        annotated.has_website_hiring_signal,
        annotated.has_recent_hiring_post,
        annotated.has_hiring_signal,
    )


def test_recent_who_is_hiring_post_is_a_hiring_signal():
    startup = create_startup("Acme")
    add_record(startup, SourceKey.HACKER_NEWS_HIRING, published_days_ago=10)

    assert hiring_status_of(startup) == (False, True, True)


def test_old_who_is_hiring_post_is_not_a_hiring_signal():
    startup = create_startup("Acme")
    add_record(startup, SourceKey.HACKER_NEWS_HIRING, HIRING_POST_MAX_AGE_DAYS + 1)

    assert hiring_status_of(startup) == (False, False, False)


def test_recent_post_from_another_source_is_not_a_hiring_signal():
    startup = create_startup("Acme")
    add_record(startup, SourceKey.HACKER_NEWS, published_days_ago=1)

    assert hiring_status_of(startup) == (False, False, False)


def test_website_signal_alone_is_a_hiring_signal():
    startup = create_startup("Acme")
    add_inspection(startup, has_hiring_signal=True)

    assert hiring_status_of(startup) == (True, False, True)


def test_both_signals_are_reported():
    startup = create_startup("Acme")
    add_inspection(startup, has_hiring_signal=True)
    add_record(startup, SourceKey.HACKER_NEWS_HIRING, published_days_ago=3)

    assert hiring_status_of(startup) == (True, True, True)


def test_startups_with_hiring_signal_can_be_filtered():
    hiring = create_startup("Hiring")
    add_record(hiring, SourceKey.HACKER_NEWS_HIRING, published_days_ago=3)
    create_startup("Quiet")

    names = Startup.objects.with_hiring_signal().filter(has_hiring_signal=True)

    assert list(names.values_list("name", flat=True)) == ["Hiring"]


def test_admin_changelist_lists_startups_with_signal_first(admin_client):
    create_startup("Quiet")
    hiring = create_startup("Hiring")
    add_record(hiring, SourceKey.HACKER_NEWS_HIRING, published_days_ago=3)

    response = admin_client.get("/admin/startups/startup/")

    assert response.status_code == 200
    listed_names = [startup.name for startup in response.context["cl"].result_list]
    assert listed_names == ["Hiring", "Quiet"]


def test_admin_changelist_filters_by_hiring_signal(admin_client):
    create_startup("Quiet")
    hiring = create_startup("Hiring")
    add_inspection(hiring, has_hiring_signal=True)

    response = admin_client.get("/admin/startups/startup/", {"hiring_signal": "yes"})

    listed_names = [startup.name for startup in response.context["cl"].result_list]
    assert listed_names == ["Hiring"]
