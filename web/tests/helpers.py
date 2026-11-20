from sources.constants import SourceKey
from sources.models import Source, SourceRecord
from startups.constants import ContactFoundVia, ContactRole
from startups.models import Contact, Startup, StartupDomain


def create_startup(name, domain="", source_key=SourceKey.HACKER_NEWS, **fields):
    startup = Startup.objects.create(
        name=name, website=f"https://{domain}" if domain else "", **fields
    )
    if domain:
        StartupDomain.objects.create(startup=startup, domain=domain, is_primary=True)
    SourceRecord.objects.create(
        source=Source.objects.get(key=source_key),
        startup=startup,
        external_id=f"{source_key}-{name}",
        url=f"https://news.ycombinator.com/item?id={startup.pk}",
        data={"name": name, "website": startup.website},
    )
    return startup


def create_contact(startup, full_name="Jane Roe", role=ContactRole.CEO, **fields):
    return Contact.objects.create(
        startup=startup,
        full_name=full_name,
        role=role,
        found_via=fields.pop("found_via", ContactFoundVia.WEBSITE),
        **fields,
    )
