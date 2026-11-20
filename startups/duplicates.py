"""Merging two startups that turned out to be the same company. Always a manual decision:
ingestion only flags possible duplicates, it never merges them."""

from django.db import transaction

from startups.contacts import find_matching_contact
from startups.merge import recompute_startup
from startups.models import Startup, WebsiteInspection


@transaction.atomic
def merge_startups(kept, duplicate):
    """Move everything of `duplicate` to `kept`, recompute `kept` and delete `duplicate`.

    `kept` keeps its status, its website inspection (when it has one) and the review of its
    contacts; contacts of `duplicate` that match one of `kept` only fill its blank fields.
    """
    if kept.pk == duplicate.pk:
        raise ValueError("A startup cannot be merged with itself")
    duplicate.domains.update(startup=kept, is_primary=False)
    duplicate.source_records.update(startup=kept)
    duplicate.analyses.update(startup=kept)
    duplicate.status_changes.update(startup=kept)
    _move_contacts(duplicate, kept)
    _move_inspection(duplicate, kept)
    Startup.objects.filter(possible_duplicate_of=duplicate).exclude(pk=kept.pk).update(
        possible_duplicate_of=kept
    )
    if kept.possible_duplicate_of_id == duplicate.pk:
        kept.possible_duplicate_of = None
    duplicate.delete()
    return recompute_startup(kept)


def dismiss_duplicate(startup):
    """They are different companies: drop the flag."""
    startup.possible_duplicate_of = None
    startup.save(update_fields=["possible_duplicate_of", "updated_at"])
    return startup


def _move_contacts(duplicate, kept):
    for contact in duplicate.contacts.all():
        existing_contact = find_matching_contact(
            kept, contact.email, contact.profile_url, contact.full_name
        )
        if existing_contact is None:
            contact.startup = kept
            contact.save(update_fields=["startup"])
            continue
        for field_name in ("full_name", "email", "profile_url"):
            if not getattr(existing_contact, field_name):
                setattr(existing_contact, field_name, getattr(contact, field_name))
        existing_contact.save()
        contact.analyses_sent.update(sent_to=existing_contact)
        contact.delete()


def _move_inspection(duplicate, kept):
    if WebsiteInspection.objects.filter(startup=kept).exists():
        WebsiteInspection.objects.filter(startup=duplicate).delete()
    else:
        WebsiteInspection.objects.filter(startup=duplicate).update(startup=kept)
