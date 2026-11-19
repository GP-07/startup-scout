from django.db import migrations

# Literal values on purpose: migrations must not change if the constants do.
AUTHOR_ROLES = {"hacker_news": "founder", "hacker_news_hiring": "other"}
HACKER_NEWS_USER_URL = "https://news.ycombinator.com/user?id={author}"
SOURCE_FOUND_VIA = "source"


def add_author_contacts(apps, schema_editor):
    """Records stored before sources reported contacts keep the post author in the payload."""
    source_record_model = apps.get_model("sources", "SourceRecord")
    contact_model = apps.get_model("startups", "Contact")
    records = source_record_model.objects.filter(source__key__in=AUTHOR_ROLES).select_related(
        "source"
    )
    for record in records:
        author = record.payload.get("author")
        if not author:
            continue
        profile_url = HACKER_NEWS_USER_URL.format(author=author)
        contact_model.objects.get_or_create(
            startup_id=record.startup_id,
            profile_url=profile_url,
            defaults={
                "role": AUTHOR_ROLES[record.source.key],
                "found_via": SOURCE_FOUND_VIA,
                "evidence_url": record.url,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("startups", "0004_website_inspection_contacts_found"),
        ("sources", "0004_hacker_news_hiring"),
    ]

    operations = [
        migrations.RunPython(add_author_contacts, migrations.RunPython.noop),
    ]
