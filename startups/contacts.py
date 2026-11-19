"""Stores the contacts found for a startup without duplicating them or undoing my review."""

from django.db.models import Q

from startups.models import Contact


def save_contacts(startup, candidates, found_via):
    """Create the candidates not known yet; return how many were created.

    A contact already stored (found before, or loaded by hand) only gets its blank fields
    filled: its name, role and review status stay as they are.
    """
    created = 0
    for candidate in candidates:
        existing_contact = _find_existing(startup, candidate)
        if existing_contact is None:
            Contact.objects.create(
                startup=startup,
                full_name=candidate.full_name,
                role=candidate.role,
                email=candidate.email,
                profile_url=candidate.profile_url,
                found_via=found_via,
                evidence_url=candidate.evidence_url,
            )
            created += 1
        else:
            _fill_blank_fields(existing_contact, candidate)
    return created


def _find_existing(startup, candidate):
    same_contact = Q()
    if candidate.email:
        same_contact |= Q(email__iexact=candidate.email)
    if candidate.profile_url:
        same_contact |= Q(profile_url=candidate.profile_url)
    if candidate.full_name:
        same_contact |= Q(full_name__iexact=candidate.full_name)
    if not same_contact:
        return None
    return startup.contacts.filter(same_contact).order_by("id").first()


def _fill_blank_fields(contact, candidate):
    changed_fields = [
        field_name
        for field_name in ("full_name", "email", "profile_url")
        if not getattr(contact, field_name) and getattr(candidate, field_name)
    ]
    for field_name in changed_fields:
        setattr(contact, field_name, getattr(candidate, field_name))
    if changed_fields:
        contact.save(update_fields=changed_fields)
