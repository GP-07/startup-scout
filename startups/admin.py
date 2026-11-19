from django.contrib import admin
from django.db import models

from startups.constants import (
    HIRING_FILTER_NO,
    HIRING_FILTER_PARAMETER,
    HIRING_FILTER_YES,
    HiringSignalOrigin,
)
from startups.models import (
    Analysis,
    Contact,
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


class WebsiteInspectionInline(admin.StackedInline):
    model = WebsiteInspection
    extra = 0
    can_delete = False


class HiringSignalFilter(admin.SimpleListFilter):
    title = "búsquedas abiertas"
    parameter_name = HIRING_FILTER_PARAMETER

    def lookups(self, request, model_admin):
        return [(HIRING_FILTER_YES, "Sí"), (HIRING_FILTER_NO, "No")]

    def queryset(self, request, queryset):
        if self.value() == HIRING_FILTER_YES:
            return queryset.filter(has_hiring_signal=True)
        if self.value() == HIRING_FILTER_NO:
            return queryset.filter(has_hiring_signal=False)
        return queryset


@admin.register(Startup)
class StartupAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "website",
        "has_hiring_signal",
        "hiring_signal_origin",
        "status",
        "first_seen_at",
    ]
    list_filter = [HiringSignalFilter, "status", "country"]
    search_fields = ["name", "website", "domains__domain"]
    raw_id_fields = ["possible_duplicate_of"]
    inlines = [StartupDomainInline, ContactInline, WebsiteInspectionInline]

    def get_queryset(self, request):
        return super().get_queryset(request).with_hiring_signal()

    def get_ordering(self, request):
        # Startups with a hiring signal first, then the newest. Set here and not in `ordering`
        # because it sorts by an annotation, which the admin checks would reject there.
        return [models.F("has_hiring_signal").desc(), "-first_seen_at"]

    @admin.display(boolean=True, description="Búsquedas abiertas", ordering="has_hiring_signal")
    def has_hiring_signal(self, startup):
        return startup.has_hiring_signal

    @admin.display(description="Señal desde")
    def hiring_signal_origin(self, startup):
        if startup.has_website_hiring_signal and startup.has_recent_hiring_post:
            return HiringSignalOrigin.BOTH.label
        if startup.has_website_hiring_signal:
            return HiringSignalOrigin.WEBSITE.label
        if startup.has_recent_hiring_post:
            return HiringSignalOrigin.HIRING_POST.label
        return ""


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
        "contacts_found",
        "inspected_at",
    ]
    list_filter = ["status", "has_hiring_signal", "hiring_signal_method", "hiring_signal_kind"]
    search_fields = ["startup__name", "hiring_signal_url"]
    raw_id_fields = ["startup"]
