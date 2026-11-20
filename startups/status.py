"""Status changes of a startup. Every change is manual (except the one done by marking an
analysis as sent) and leaves a `StatusChange` in the history."""

from django.db import transaction

from startups.constants import StartupStatus
from startups.exceptions import DiscardReasonRequiredError
from startups.models import StatusChange


@transaction.atomic
def change_status(startup, to_status, note=""):
    """Move the startup to `to_status` and record it. Discarding needs a reason (`note`)."""
    note = note.strip()
    if to_status == startup.status:
        return startup
    if to_status == StartupStatus.DISCARDED and not note:
        raise DiscardReasonRequiredError()
    StatusChange.objects.create(
        startup=startup, from_status=startup.status, to_status=to_status, note=note
    )
    startup.status = to_status
    startup.discard_reason = note if to_status == StartupStatus.DISCARDED else ""
    startup.save(update_fields=["status", "discard_reason", "updated_at"])
    return startup


def discard_startup(startup, reason):
    return change_status(startup, StartupStatus.DISCARDED, note=reason)
