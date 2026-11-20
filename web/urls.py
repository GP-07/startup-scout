from django.urls import path

from web.views import analyses, contacts, duplicates, runs, startups

app_name = "web"

urlpatterns = [
    path("", startups.startup_list, name="startup_list"),
    path("startups/new/", startups.startup_create, name="startup_create"),
    path("startups/<int:pk>/", startups.startup_detail, name="startup_detail"),
    path("startups/<int:pk>/discard/", startups.startup_discard, name="startup_discard"),
    path("startups/<int:pk>/status/", startups.startup_status, name="startup_status"),
    path("startups/<int:pk>/contacts/", contacts.contact_create, name="contact_create"),
    path("contacts/<int:pk>/review/", contacts.contact_review, name="contact_review"),
    path("startups/<int:pk>/analyses/new/", analyses.analysis_create, name="analysis_create"),
    path("analyses/<int:pk>/edit/", analyses.analysis_edit, name="analysis_edit"),
    path("analyses/<int:pk>/delete/", analyses.analysis_delete, name="analysis_delete"),
    path("analyses/<int:pk>/sent/", analyses.analysis_mark_sent, name="analysis_mark_sent"),
    path("analyses/<int:pk>/unsent/", analyses.analysis_unmark_sent, name="analysis_unmark_sent"),
    path("duplicates/", duplicates.duplicate_list, name="duplicate_list"),
    path("duplicates/<int:pk>/", duplicates.duplicate_compare, name="duplicate_compare"),
    path("duplicates/<int:pk>/merge/", duplicates.duplicate_merge, name="duplicate_merge"),
    path("duplicates/<int:pk>/dismiss/", duplicates.duplicate_dismiss, name="duplicate_dismiss"),
    path("runs/", runs.run_list, name="run_list"),
]
