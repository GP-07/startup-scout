from django.core.management.base import BaseCommand

from startups.domain_cleanup import prune_platform_domains


class Command(BaseCommand):
    help = (
        "Remove stored domains that belong to platforms (per the current identity rules) and "
        "reassign each affected startup its own domain from its source records."
    )

    def handle(self, *args, **options):
        result = prune_platform_domains()
        for domain in result.removed_domains:
            self.stdout.write(f"  removed: {domain}")
        for domain in result.reassigned_domains:
            self.stdout.write(f"  reassigned: {domain}")
        self.stdout.write(
            self.style.SUCCESS(
                f"Removed {len(result.removed_domains)} platform domains, "
                f"reassigned {len(result.reassigned_domains)}. "
                "Run inspect_websites to inspect the reassigned ones."
            )
        )
