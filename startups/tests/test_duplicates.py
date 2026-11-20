import pytest

from sources.constants import SourceKey
from sources.models import Source, SourceRecord
from startups.constants import ContactFoundVia, ContactStatus, InspectionStatus
from startups.duplicates import dismiss_duplicate, merge_startups
from startups.models import (
    Analysis,
    Contact,
    Startup,
    StartupDomain,
    StatusChange,
    WebsiteInspection,
)

pytestmark = pytest.mark.django_db


def create_startup(name, domain, source_key, external_id, **data):
    startup = Startup.objects.create(name=name)
    StartupDomain.objects.create(startup=startup, domain=domain, is_primary=True)
    SourceRecord.objects.create(
        source=Source.objects.get(key=source_key),
        startup=startup,
        external_id=external_id,
        data={"name": name, "website": f"https://{domain}", **data},
    )
    return startup


def test_merge_moves_everything_to_the_kept_startup_and_recomputes_it():
    kept = create_startup("Acme", "acme.com", SourceKey.HACKER_NEWS, "hn-1")
    duplicate = create_startup(
        "Acme Labs", "acmelabs.io", SourceKey.MANUAL, "acmelabs.io", city="Barcelona"
    )
    duplicate.possible_duplicate_of = kept
    duplicate.save()
    Contact.objects.create(
        startup=duplicate, full_name="Jane Roe", found_via=ContactFoundVia.WEBSITE
    )
    Analysis.objects.create(startup=duplicate, title="Ideas", body="...")
    StatusChange.objects.create(startup=duplicate, from_status="new", to_status="reviewing")
    WebsiteInspection.objects.create(startup=duplicate, status=InspectionStatus.DONE)

    merge_startups(kept=kept, duplicate=duplicate)

    assert not Startup.objects.filter(pk=duplicate.pk).exists()
    kept.refresh_from_db()
    assert list(kept.domains.values_list("domain", "is_primary")) == [
        ("acme.com", True),
        ("acmelabs.io", False),
    ]
    assert kept.source_records.count() == 2
    assert kept.name == "Acme Labs"  # The manual record has the highest priority.
    assert kept.city == "Barcelona"
    assert kept.contacts.get().full_name == "Jane Roe"
    assert kept.analyses.count() == 1
    assert kept.status_changes.count() == 1
    assert kept.website_inspection.status == InspectionStatus.DONE


def test_merge_does_not_duplicate_contacts_and_keeps_the_kept_review():
    kept = create_startup("Acme", "acme.com", SourceKey.HACKER_NEWS, "hn-1")
    duplicate = create_startup("Acme", "acme.io", SourceKey.MANUAL, "acme.io")
    Contact.objects.create(
        startup=kept,
        full_name="Jane Roe",
        found_via=ContactFoundVia.MANUAL,
        status=ContactStatus.CONFIRMED,
    )
    Contact.objects.create(
        startup=duplicate,
        full_name="Jane Roe",
        email="jane@acme.io",
        found_via=ContactFoundVia.WEBSITE,
    )

    merge_startups(kept=kept, duplicate=duplicate)

    jane = kept.contacts.get()
    assert jane.status == ContactStatus.CONFIRMED
    assert jane.email == "jane@acme.io"


def test_merge_keeps_the_kept_inspection_and_repoints_other_duplicates():
    kept = create_startup("Acme", "acme.com", SourceKey.HACKER_NEWS, "hn-1")
    duplicate = create_startup("Acme", "acme.io", SourceKey.MANUAL, "acme.io")
    third = create_startup("Acme", "acme.dev", SourceKey.HACKER_NEWS, "hn-3")
    third.possible_duplicate_of = duplicate
    third.save()
    WebsiteInspection.objects.create(startup=kept, status=InspectionStatus.DONE)
    WebsiteInspection.objects.create(startup=duplicate, status=InspectionStatus.FAILED)

    merge_startups(kept=kept, duplicate=duplicate)

    kept.refresh_from_db()
    third.refresh_from_db()
    assert kept.website_inspection.status == InspectionStatus.DONE
    assert third.possible_duplicate_of == kept


def test_merging_a_startup_with_itself_is_rejected():
    startup = create_startup("Acme", "acme.com", SourceKey.HACKER_NEWS, "hn-1")

    with pytest.raises(ValueError):
        merge_startups(kept=startup, duplicate=startup)


def test_dismissing_clears_the_possible_duplicate_flag():
    kept = create_startup("Acme", "acme.com", SourceKey.HACKER_NEWS, "hn-1")
    other = create_startup("Acme", "acme.io", SourceKey.MANUAL, "acme.io")
    other.possible_duplicate_of = kept
    other.save()

    dismiss_duplicate(other)

    other.refresh_from_db()
    assert other.possible_duplicate_of is None
