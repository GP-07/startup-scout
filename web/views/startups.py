from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from sources.constants import SourceKey
from sources.manual_entry import add_startup_manually
from startups.exceptions import DiscardReasonRequiredError, InvalidWebsiteError
from startups.models import Startup
from startups.status import change_status, discard_startup
from web.constants import (
    INVALID_WEBSITE_MESSAGE,
    MERGED_FIELD_LABELS,
    MISSING_DISCARD_REASON_MESSAGE,
    STARTUPS_PER_PAGE,
)
from web.filters import filter_startups, startup_list_queryset
from web.forms import (
    AnalysisForm,
    ContactForm,
    DiscardForm,
    ManualEntryForm,
    StartupFilterForm,
    StatusForm,
)
from web.htmx import is_htmx
from web.views.analyses import analyses_context
from web.views.contacts import contacts_context


def startup_list(request):
    filter_form = StartupFilterForm(request.GET or None)
    filters = filter_form.cleaned_data if filter_form.is_valid() else {}
    startups = filter_startups(startup_list_queryset(), filters)
    page_obj = Paginator(startups, STARTUPS_PER_PAGE).get_page(request.GET.get("page"))
    query_without_page = request.GET.copy()
    query_without_page.pop("page", None)
    context = {
        "filter_form": filter_form,
        "page_obj": page_obj,
        "query_without_page": query_without_page.urlencode(),
    }
    template = "web/partials/startup_results.html" if is_htmx(request) else "web/startup_list.html"
    return render(request, template, context)


@require_POST
def startup_discard(request, pk):
    startup = get_object_or_404(Startup, pk=pk)
    form = DiscardForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "web/partials/startup_row.html",
            {"startup": _listed(startup), "discard_error": MISSING_DISCARD_REASON_MESSAGE},
            status=400,
        )
    discard_startup(startup, form.cleaned_data["reason"])
    return render(request, "web/partials/startup_row.html", {"startup": _listed(startup)})


def startup_detail(request, pk):
    startup = get_object_or_404(Startup.objects.with_hiring_signal(), pk=pk)
    source_records = startup.source_records.select_related("source").order_by("-first_seen_at")
    context = {
        "startup": startup,
        "merged_fields": _merged_fields(startup),
        "domains": startup.domains.all(),
        "source_records": source_records,
        "hiring_posts": [
            record for record in source_records if record.source.key == SourceKey.HACKER_NEWS_HIRING
        ],
        "inspection": getattr(startup, "website_inspection", None),
        "status_form": StatusForm(initial={"status": startup.status}),
        "status_changes": startup.status_changes.all(),
        "possible_duplicates": startup.possible_duplicates.all(),
        "analysis_form": AnalysisForm(),
        **contacts_context(startup, ContactForm()),
        **analyses_context(startup),
    }
    return render(request, "web/startup_detail.html", context)


@require_POST
def startup_status(request, pk):
    startup = get_object_or_404(Startup, pk=pk)
    form = StatusForm(request.POST)
    if form.is_valid():
        try:
            change_status(startup, form.cleaned_data["status"], note=form.cleaned_data["note"])
        except DiscardReasonRequiredError:
            messages.error(request, MISSING_DISCARD_REASON_MESSAGE)
    return redirect("web:startup_detail", pk=startup.pk)


def startup_create(request):
    form = ManualEntryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            result = add_startup_manually(
                form.cleaned_data["website"], name=form.cleaned_data["name"]
            )
        except InvalidWebsiteError:
            form.add_error("website", INVALID_WEBSITE_MESSAGE)
        else:
            if result.created:
                messages.success(request, "Startup creada. Su web se va a inspeccionar en breve.")
            else:
                messages.info(request, "Esa web ya estaba cargada: te llevo a su ficha.")
            return redirect("web:startup_detail", pk=result.startup.pk)
    return render(request, "web/startup_create.html", {"form": form})


def _listed(startup):
    """The startup with the annotations a list row shows."""
    return startup_list_queryset().get(pk=startup.pk)


def _merged_fields(startup):
    source_labels = dict(SourceKey.choices)
    return [
        {
            "label": label,
            "value": getattr(startup, field_name),
            "source": source_labels.get(startup.field_sources.get(field_name), ""),
        }
        for field_name, label in MERGED_FIELD_LABELS
    ]
