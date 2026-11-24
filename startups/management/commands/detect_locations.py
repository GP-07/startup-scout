from collections import Counter

from django.core.management.base import BaseCommand

from startups.headquarters import detect_location
from startups.models import Startup


class Command(BaseCommand):
    help = (
        "Detect where startups are established from the evidence already stored (no requests). "
        "By default only those never detected; locations corrected by hand are kept."
    )

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="Detect them all again.")

    def handle(self, *args, **options):
        startups = Startup.objects.order_by("id")
        if not options["all"]:
            startups = startups.filter(location_detected_at__isnull=True)
        sources = Counter()
        for startup in startups.iterator():
            detect_location(startup)
            sources[startup.location_source or "unknown"] += 1
        summary = ", ".join(f"{source}: {count}" for source, count in sorted(sources.items()))
        self.stdout.write(self.style.SUCCESS(f"Detected {sum(sources.values())} · {summary}"))
