from django.core.management.base import BaseCommand, CommandError

from sources.models import Source
from sources.runner import SourceRunner


class Command(BaseCommand):
    help = "Run one source now, outside the daily schedule. Example: run_source hacker_news"

    def add_arguments(self, parser):
        parser.add_argument("source_key")

    def handle(self, *args, **options):
        try:
            source = Source.objects.get(key=options["source_key"])
        except Source.DoesNotExist as error:
            raise CommandError(f"Unknown source '{options['source_key']}'") from error
        if not source.enabled:
            raise CommandError(f"Source '{source.key}' is disabled")

        source_run = SourceRunner().run(source)
        self.stdout.write(
            f"{source.key}: {source_run.status} · seen {source_run.items_seen} · "
            f"new {source_run.items_new}"
        )
        if source_run.error:
            self.stdout.write(self.style.WARNING(source_run.error))
