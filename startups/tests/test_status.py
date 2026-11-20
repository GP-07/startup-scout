import pytest

from startups.constants import StartupStatus
from startups.exceptions import DiscardReasonRequiredError
from startups.models import Startup
from startups.status import change_status, discard_startup

pytestmark = pytest.mark.django_db


def test_status_change_is_recorded_in_the_history():
    startup = Startup.objects.create(name="Acme")

    change_status(startup, StartupStatus.REVIEWING, note="Looks promising")

    startup.refresh_from_db()
    assert startup.status == StartupStatus.REVIEWING
    change = startup.status_changes.get()
    assert (change.from_status, change.to_status, change.note) == (
        StartupStatus.NEW,
        StartupStatus.REVIEWING,
        "Looks promising",
    )


def test_changing_to_the_same_status_records_nothing():
    startup = Startup.objects.create(name="Acme")

    change_status(startup, StartupStatus.NEW)

    assert not startup.status_changes.exists()


def test_discard_requires_a_reason_and_stores_it():
    startup = Startup.objects.create(name="Acme")

    with pytest.raises(DiscardReasonRequiredError):
        discard_startup(startup, reason="  ")
    discard_startup(startup, reason="Agency, not a product")

    startup.refresh_from_db()
    assert startup.status == StartupStatus.DISCARDED
    assert startup.discard_reason == "Agency, not a product"
    assert startup.status_changes.get().note == "Agency, not a product"


def test_changing_status_through_change_status_to_discarded_also_requires_a_reason():
    startup = Startup.objects.create(name="Acme")

    with pytest.raises(DiscardReasonRequiredError):
        change_status(startup, StartupStatus.DISCARDED)


def test_reverting_a_discard_clears_the_reason():
    startup = Startup.objects.create(name="Acme")
    discard_startup(startup, reason="Agency")

    change_status(startup, StartupStatus.NEW, note="It is a product after all")

    startup.refresh_from_db()
    assert startup.status == StartupStatus.NEW
    assert startup.discard_reason == ""
    assert startup.status_changes.count() == 2
