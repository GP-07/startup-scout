import pytest

from sources.constants import SourceKey
from sources.models import Source, SourceRecord
from startups.constants import InspectionStatus
from startups.domain_cleanup import prune_platform_domains
from startups.models import Startup, StartupDomain, WebsiteInspection

pytestmark = pytest.mark.django_db


def create_legacy_startup(name, stored_domain, website):
    """A startup ingested before its platform domain was recognized as one."""
    startup = Startup.objects.create(name=name, website=website)
    StartupDomain.objects.create(startup=startup, domain=stored_domain, is_primary=True)
    SourceRecord.objects.create(
        source=Source.objects.get(key=SourceKey.HACKER_NEWS),
        startup=startup,
        external_id=name,
        data={"name": name, "website": website},
    )
    WebsiteInspection.objects.create(
        startup=startup, status=InspectionStatus.DONE, has_hiring_signal=True
    )
    return startup


def test_platform_domain_is_removed_with_its_inspection():
    plugin = create_legacy_startup(
        "Acme plugin", "jetbrains.com", "https://plugins.jetbrains.com/plugin/1-acme"
    )

    result = prune_platform_domains()

    assert result.removed_domains == ["jetbrains.com"]
    assert result.reassigned_domains == []
    assert not plugin.domains.exists()
    assert not WebsiteInspection.objects.filter(startup=plugin).exists()


def test_shared_host_domain_is_replaced_by_the_startup_subdomain():
    app = create_legacy_startup("Acme app", "bolt.host", "https://acme-app.bolt.host")

    result = prune_platform_domains()

    assert result.reassigned_domains == ["acme-app.bolt.host"]
    assert list(app.domains.values_list("domain", "is_primary")) == [("acme-app.bolt.host", True)]


def test_own_domains_are_left_untouched():
    own = create_legacy_startup("Acme", "acme.com", "https://acme.com")

    result = prune_platform_domains()

    assert result.removed_domains == []
    assert list(own.domains.values_list("domain", flat=True)) == ["acme.com"]
    assert WebsiteInspection.objects.filter(startup=own).exists()


def test_remaining_alias_becomes_primary_when_the_platform_domain_was_primary():
    startup = create_legacy_startup(
        "Acme", "myworkdayjobs.com", "https://go.acme.com/jobs-redirect"
    )
    StartupDomain.objects.create(startup=startup, domain="acme.com", is_primary=False)

    result = prune_platform_domains()

    assert result.removed_domains == ["myworkdayjobs.com"]
    assert result.reassigned_domains == ["acme.com"]
    assert list(startup.domains.values_list("domain", "is_primary")) == [("acme.com", True)]
