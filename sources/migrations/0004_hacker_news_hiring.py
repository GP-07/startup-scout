from datetime import UTC, datetime

from django.db import migrations, models

# Literal values on purpose: migrations must not change if the constants do.
HACKER_NEWS_HIRING_KEY = "hacker_news_hiring"
HACKER_NEWS_HIRING_NAME = "HN Who is hiring"
HACKER_NEWS_KEY = "hacker_news"
TIMESTAMP_PAYLOAD_KEY = "created_at_i"


def create_hacker_news_hiring_source(apps, schema_editor):
    source_model = apps.get_model("sources", "Source")
    source_model.objects.get_or_create(
        key=HACKER_NEWS_HIRING_KEY, defaults={"name": HACKER_NEWS_HIRING_NAME, "config": {}}
    )


def delete_hacker_news_hiring_source(apps, schema_editor):
    source_record_model = apps.get_model("sources", "SourceRecord")
    source_model = apps.get_model("sources", "Source")
    source_record_model.objects.filter(source__key=HACKER_NEWS_HIRING_KEY).delete()
    source_model.objects.filter(key=HACKER_NEWS_HIRING_KEY).delete()


def backfill_hacker_news_published_at(apps, schema_editor):
    """Hacker News records already stored keep their post date in the payload."""
    source_record_model = apps.get_model("sources", "SourceRecord")
    records = source_record_model.objects.filter(
        source__key=HACKER_NEWS_KEY, published_at__isnull=True
    )
    for record in records:
        timestamp = record.payload.get(TIMESTAMP_PAYLOAD_KEY)
        if timestamp:
            record.published_at = datetime.fromtimestamp(timestamp, tz=UTC)
            record.save(update_fields=["published_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("sources", "0003_remove_startupxplore"),
    ]

    operations = [
        migrations.AddField(
            model_name="sourcerecord",
            name="published_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="source",
            name="key",
            field=models.SlugField(
                choices=[
                    ("hacker_news", "Hacker News"),
                    ("hacker_news_hiring", "HN Who is hiring"),
                    ("manual", "Alta manual"),
                ],
                unique=True,
            ),
        ),
        migrations.RunPython(create_hacker_news_hiring_source, delete_hacker_news_hiring_source),
        migrations.RunPython(backfill_hacker_news_published_at, migrations.RunPython.noop),
    ]
