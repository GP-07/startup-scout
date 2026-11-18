from django.db import migrations

# Literal values on purpose: migrations must not change if the constants do.
INITIAL_SOURCES = (
    ("hacker_news", "Hacker News", {"tags": ["show_hn", "launch_hn"]}),
    ("startupxplore", "Startupxplore", {}),
    ("manual", "Alta manual", {}),
)


def create_initial_sources(apps, schema_editor):
    source_model = apps.get_model("sources", "Source")
    for key, name, config in INITIAL_SOURCES:
        source_model.objects.get_or_create(key=key, defaults={"name": name, "config": config})


def delete_initial_sources(apps, schema_editor):
    source_model = apps.get_model("sources", "Source")
    source_model.objects.filter(key__in=[key for key, _, _ in INITIAL_SOURCES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("sources", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_initial_sources, delete_initial_sources),
    ]
