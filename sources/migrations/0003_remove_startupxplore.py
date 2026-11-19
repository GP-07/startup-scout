from django.db import migrations, models

# Startupxplore was dropped as a source: its terms of use (7.3, 7.4) forbid reproducing its
# database, in whole or in part, without written consent. See docs/startup-scout-design.md §2.
STARTUPXPLORE_KEY = "startupxplore"


def delete_startupxplore(apps, schema_editor):
    source_model = apps.get_model("sources", "Source")
    source_record_model = apps.get_model("sources", "SourceRecord")
    source_record_model.objects.filter(source__key=STARTUPXPLORE_KEY).delete()
    source_model.objects.filter(key=STARTUPXPLORE_KEY).delete()


def restore_startupxplore(apps, schema_editor):
    source_model = apps.get_model("sources", "Source")
    source_model.objects.get_or_create(
        key=STARTUPXPLORE_KEY, defaults={"name": "Startupxplore", "enabled": False}
    )


class Migration(migrations.Migration):
    dependencies = [
        ("sources", "0002_seed_initial_sources"),
    ]

    operations = [
        migrations.RunPython(delete_startupxplore, restore_startupxplore),
        migrations.AlterField(
            model_name="source",
            name="key",
            field=models.SlugField(
                choices=[("hacker_news", "Hacker News"), ("manual", "Alta manual")],
                max_length=50,
                unique=True,
            ),
        ),
    ]
