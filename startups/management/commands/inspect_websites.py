from collections import Counter

from django.core.management.base import BaseCommand

from startups.constants import ALREADY_INSPECTED_STATUSES, INSPECTION_PROGRESS_EVERY
from startups.inspection_stats import spa_shell_stats
from startups.models import Startup
from startups.website_inspection import WebsiteInspectionService


class Command(BaseCommand):
    help = (
        "Inspect the websites of startups with their own domain, looking for open positions. "
        "By default only those never inspected (or pending or failed)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="Inspect them all again.")
        parser.add_argument("--limit", type=int, help="Inspect at most this many startups.")
        parser.add_argument(
            "--stats",
            action="store_true",
            help=(
                "Inspect nothing: list the inspections without hiring signal whose home looks "
                "like an empty single-page-app shell, to review them by hand."
            ),
        )

    def handle(self, *args, **options):
        if options["stats"]:
            self._print_spa_shell_stats()
            return
        startups = Startup.objects.filter(domains__is_primary=True).distinct().order_by("id")
        if not options["all"]:
            startups = startups.exclude(website_inspection__status__in=ALREADY_INSPECTED_STATUSES)
        if options["limit"]:
            startups = startups[: options["limit"]]

        service = WebsiteInspectionService()
        statuses = Counter()
        hiring_signals = 0
        contacts_found = 0
        startups_to_inspect = list(startups)
        for position, startup in enumerate(startups_to_inspect, start=1):
            inspection = service.inspect(startup)
            if inspection is None:
                continue
            statuses[inspection.status] += 1
            contacts_found += inspection.contacts_found
            if inspection.has_hiring_signal:
                hiring_signals += 1
                self.stdout.write(f"  hiring: {startup.name} -> {inspection.hiring_signal_url}")
            if position % INSPECTION_PROGRESS_EVERY == 0:
                self.stdout.write(f"{position}/{len(startups_to_inspect)} inspected")

        summary = ", ".join(f"{status}: {count}" for status, count in sorted(statuses.items()))
        self.stdout.write(
            self.style.SUCCESS(
                f"Inspected {len(startups_to_inspect)} · with hiring signal: {hiring_signals}"
                f" · contacts found: {contacts_found} · {summary}"
            )
        )

    def _print_spa_shell_stats(self):
        stats = spa_shell_stats()
        for inspection in stats.probable_shells:
            self.stdout.write(
                f"  {inspection.startup.name} -> {inspection.startup.website}"
                f" (text: {inspection.home_text_length}, links: {inspection.home_link_count},"
                f" app root: {inspection.home_has_app_root})"
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Without hiring signal: {stats.without_signal}"
                f" · probable single-page-app shells: {len(stats.probable_shells)}"
                f" · not measured yet: {stats.without_metrics}"
            )
        )
        if stats.without_metrics:
            self.stdout.write("Run inspect_websites --all to measure the ones not measured yet.")
