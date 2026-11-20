"""Marking my analyses as sent. Emails are sent from my own mailbox, outside the app."""

from django.db import transaction
from django.utils import timezone

from startups.constants import ANALYSIS_SENT_NOTE, STATUSES_AFTER_CONTACT, StartupStatus
from startups.exceptions import ForeignContactError
from startups.status import change_status


@transaction.atomic
def mark_analysis_sent(analysis, sent_at=None, sent_to=None):
    """Record when (now by default) and to whom it was sent; the startup becomes `contacted`."""
    if sent_to is not None and sent_to.startup_id != analysis.startup_id:
        raise ForeignContactError(sent_to, analysis.startup)
    analysis.sent_at = sent_at or timezone.now()
    analysis.sent_to = sent_to
    analysis.save(update_fields=["sent_at", "sent_to", "updated_at"])
    startup = analysis.startup
    if startup.status not in STATUSES_AFTER_CONTACT:
        change_status(
            startup, StartupStatus.CONTACTED, note=ANALYSIS_SENT_NOTE.format(title=analysis.title)
        )
    return analysis


def unmark_analysis_sent(analysis):
    """Undo a mark made by mistake. The status and its history are left as they are."""
    analysis.sent_at = None
    analysis.sent_to = None
    analysis.save(update_fields=["sent_at", "sent_to", "updated_at"])
    return analysis
