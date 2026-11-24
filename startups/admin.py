from django.contrib import admin
from django.db import models

from startups.constants import OpeningsStatus
from startups.models import (
    Analysis,
    BlacklistedDomain,
    Contact,
    JobOpening,
    Startup,
    StartupDomain,
    StatusChange,
    WebsiteInspection,
)


class StartupDomainInline(admin.TabularInline):
    model = StartupDomain
    extra = 0


class ContactInline(admin.TabularInline):
    model = Contact
    extra = 0
    fields = ["full_name", "role", "email", "profile_url", "found_via", "evidence_url", "status"]


class JobOpeningInline(admin.TabularInline):
    model = JobOpening
    extra = 0
    fields = ["title", "location", "is_remote", "published_at", "origin", "url"]


class WebsiteInspectionInline(admin.StackedInline):
    model = WebsiteInspection
    extra = 0
    can_delete = False


@admin.register(Startup)
class StartupAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "website",
        "openings_state",
        "openings_count",
        "hq_country",
        "hq_timezone",
        "status",
        "first_seen_at",
    ]
    list_filter = [
        "website_inspection__openings_status",
        "status",
        "location_source",
        "hq_country",
    ]
    search_fields = ["name", "website", "domains__domain"]
    raw_id_fields = ["possible_duplicate_of"]
    inlines = [StartupDomainInline, JobOpeningInline, ContactInline, WebsiteInspectionInline]

    def get_queryset(self, request):
        return super().get_queryset(request).with_openings()

    def get_ordering(self, request):
        # Startups with active openings first, then the newest. Set here and not in `ordering`
        # because it sorts by an annotation, which the admin checks would reject there.
        return [models.F("openings_count").desc(), "-first_seen_at"]

    @admin.display(description="Búsquedas", ordering="openings_state")
    def openings_state(self, startup):
        return OpeningsStatus(startup.openings_state).label

    @admin.display(description="Activas", ordering="openings_count")
    def openings_count(self, startup):
        return startup.openings_count


@admin.register(JobOpening)
class JobOpeningAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "startup",
        "location",
        "country",
        "timezone_name",
        "is_remote",
        "published_at",
        "origin",
    ]
    list_filter = ["origin", "is_remote"]
    search_fields = ["title", "startup__name", "location"]
    raw_id_fields = ["startup"]
    list_select_related = ["startup"]


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ["startup", "full_name", "role", "email", "profile_url", "found_via", "status"]
    list_filter = ["role", "status", "found_via"]
    search_fields = ["startup__name", "full_name", "email", "profile_url"]
    raw_id_fields = ["startup"]
    list_select_related = ["startup"]


@admin.register(Analysis)
class AnalysisAdmin(admin.ModelAdmin):
    list_display = ["startup", "title", "sent_at", "created_at"]
    raw_id_fields = ["startup", "sent_to"]


@admin.register(StatusChange)
class StatusChangeAdmin(admin.ModelAdmin):
    list_display = ["startup", "from_status", "to_status", "changed_at"]
    raw_id_fields = ["startup"]


@admin.register(WebsiteInspection)
class WebsiteInspectionAdmin(admin.ModelAdmin):
    list_display = [
        "startup",
        "status",
        "has_hiring_signal",
        "hiring_signal_method",
        "hiring_signal_kind",
        "hiring_signal_url",
        "openings_status",
        "contacts_found",
        "inspected_at",
    ]
    list_filter = [
        "status",
        "has_hiring_signal",
        "openings_status",
        "hiring_signal_method",
        "hiring_signal_kind",
    ]
    search_fields = ["startup__name", "hiring_signal_url"]
    raw_id_fields = ["startup"]


@admin.register(BlacklistedDomain)
class BlacklistedDomainAdmin(admin.ModelAdmin):
    list_display = ["domain", "reason", "created_at"]
    search_fields = ["domain", "reason"]
