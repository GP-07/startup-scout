from collections import Counter

from django.core.management.base import BaseCommand

from startups.constants import INSPECTION_PROGRESS_EVERY
from startups.openings import OpeningsVerifier, startups_to_verify


class Command(BaseCommand):
    help = (
        "Check whether the startups with a hiring signal or a 'Who is hiring?' post publish "
        "openings today. By default only those never checked."
    )

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="Check them all again.")
        parser.add_argument("--limit", type=int, help="Check at most this many startups.")

    def handle(self, *args, **options):
        startups = list(startups_to_verify(include_checked=options["all"]))
        if options["limit"]:
            startups = startups[: options["limit"]]
        verifier = OpeningsVerifier()
        statuses = Counter()
        for position, startup in enumerate(startups, start=1):
            inspection = verifier.verify(startup)
            statuses[inspection.openings_status] += 1
            if position % INSPECTION_PROGRESS_EVERY == 0:
                self.stdout.write(f"{position}/{len(startups)} checked")
        summary = ", ".join(f"{status}: {count}" for status, count in sorted(statuses.items()))
        self.stdout.write(self.style.SUCCESS(f"Checked {len(startups)} · {summary}"))
