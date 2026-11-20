from datetime import UTC, datetime

import pytest

from startups.analyses import mark_analysis_sent, unmark_analysis_sent
from startups.constants import ContactFoundVia, StartupStatus
from startups.exceptions import ForeignContactError
from startups.models import Analysis, Contact, Startup
from startups.status import change_status

pytestmark = pytest.mark.django_db

SENT_AT = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)


def create_analysis(startup=None):
    startup = startup or Startup.objects.create(name="Acme")
    return Analysis.objects.create(startup=startup, title="Onboarding ideas", body="# Ideas")


def create_contact(startup):
    return Contact.objects.create(
        startup=startup, full_name="Jane Roe", found_via=ContactFoundVia.WEBSITE
    )


def test_marking_sent_stores_date_and_contact_and_moves_startup_to_contacted():
    analysis = create_analysis()
    jane = create_contact(analysis.startup)

    mark_analysis_sent(analysis, sent_at=SENT_AT, sent_to=jane)

    analysis.refresh_from_db()
    assert (analysis.sent_at, analysis.sent_to) == (SENT_AT, jane)
    startup = analysis.startup
    startup.refresh_from_db()
    assert startup.status == StartupStatus.CONTACTED
    assert "Onboarding ideas" in startup.status_changes.get().note


def test_marking_sent_without_date_uses_now():
    analysis = create_analysis()

    mark_analysis_sent(analysis)

    assert analysis.sent_at is not None


def test_startup_that_already_replied_keeps_its_status():
    startup = Startup.objects.create(name="Acme")
    change_status(startup, StartupStatus.REPLIED)
    analysis = create_analysis(startup)

    mark_analysis_sent(analysis, sent_at=SENT_AT)

    startup.refresh_from_db()
    assert startup.status == StartupStatus.REPLIED
    assert startup.status_changes.count() == 1


def test_contact_of_another_startup_is_rejected():
    analysis = create_analysis()
    stranger = create_contact(Startup.objects.create(name="Other"))

    with pytest.raises(ForeignContactError):
        mark_analysis_sent(analysis, sent_at=SENT_AT, sent_to=stranger)


def test_unmarking_clears_the_sending_but_keeps_the_history():
    analysis = create_analysis()
    mark_analysis_sent(analysis, sent_at=SENT_AT, sent_to=create_contact(analysis.startup))

    unmark_analysis_sent(analysis)

    analysis.refresh_from_db()
    assert (analysis.sent_at, analysis.sent_to) == (None, None)
    assert analysis.startup.status_changes.count() == 1
