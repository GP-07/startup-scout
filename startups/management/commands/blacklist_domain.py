from django.core.management.base import BaseCommand, CommandError

from startups.blacklist import blacklist_domain, blacklist_startup
from startups.constants import BLACKLIST_DEFAULT_REASON
from startups.domains import normalize_domain
from startups.exceptions import InvalidWebsiteError
from startups.models import Startup


class Command(BaseCommand):
    help = (
        "Blacklist a site that is not a startup (a job board the rules could not detect): its "
        "startup, if any, is discarded and never inspected again."
    )

    def add_arguments(self, parser):
        parser.add_argument("website", help="A URL or a domain, such as frameworkheroes.com.")
        parser.add_argument("--reason", default=BLACKLIST_DEFAULT_REASON)

    def handle(self, *args, **options):
        try:
            domain = normalize_domain(options["website"])
        except InvalidWebsiteError as error:
            raise CommandError(str(error)) from error
        startup = Startup.objects.filter(domains__domain=domain).first()
        if startup is None:
            blacklist_domain(domain, options["reason"])
            self.stdout.write(self.style.SUCCESS(f"Blacklisted {domain} (no startup with it)"))
            return
        blacklist_startup(startup, options["reason"])
        self.stdout.write(self.style.SUCCESS(f"Blacklisted {domain}: discarded {startup.name}"))
