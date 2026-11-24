from django.core.management.base import BaseCommand

from startups.openings import prune_unwanted_openings


class Command(BaseCommand):
    help = (
        "Discard the stored openings that are not software roles I look for or that require a "
        "language besides English and Spanish (no requests). Run it after changing those "
        "keywords in startups/constants.py; openings discarded before come back only with "
        "verify_openings --all."
    )

    def handle(self, *args, **options):
        discarded, emptied = prune_unwanted_openings()
        self.stdout.write(
            self.style.SUCCESS(
                f"Discarded {discarded} openings · startups left without openings: {emptied}"
            )
        )
