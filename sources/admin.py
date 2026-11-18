from django.contrib import admin

from sources.models import Source, SourceRecord, SourceRun


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ["name", "key", "enabled"]


@admin.register(SourceRecord)
class SourceRecordAdmin(admin.ModelAdmin):
    list_display = ["source", "external_id", "startup", "fetched_at"]
    list_filter = ["source"]
    search_fields = ["external_id", "startup__name"]
    raw_id_fields = ["startup"]


@admin.register(SourceRun)
class SourceRunAdmin(admin.ModelAdmin):
    list_display = ["source", "status", "started_at", "items_seen", "items_new"]
    list_filter = ["source", "status"]
