from django.contrib import admin

from startups.models import Analysis, Contact, Startup, StartupDomain, StatusChange


class StartupDomainInline(admin.TabularInline):
    model = StartupDomain
    extra = 0


@admin.register(Startup)
class StartupAdmin(admin.ModelAdmin):
    list_display = ["name", "website", "country", "status", "first_seen_at"]
    list_filter = ["status", "country"]
    search_fields = ["name", "website", "domains__domain"]
    raw_id_fields = ["possible_duplicate_of"]
    inlines = [StartupDomainInline]


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ["startup", "full_name", "role", "email", "status"]
    list_filter = ["role", "status", "found_via"]
    raw_id_fields = ["startup"]


@admin.register(Analysis)
class AnalysisAdmin(admin.ModelAdmin):
    list_display = ["startup", "title", "sent_at", "created_at"]
    raw_id_fields = ["startup", "sent_to"]


@admin.register(StatusChange)
class StatusChangeAdmin(admin.ModelAdmin):
    list_display = ["startup", "from_status", "to_status", "changed_at"]
    raw_id_fields = ["startup"]
