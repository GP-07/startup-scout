from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from startups.duplicates import dismiss_duplicate, merge_startups
from startups.models import Startup
from web.forms import MergeForm


def duplicate_list(request):
    flagged = Startup.objects.filter(possible_duplicate_of__isnull=False).select_related(
        "possible_duplicate_of"
    )
    return render(request, "web/duplicate_list.html", {"flagged_startups": flagged})


def duplicate_compare(request, pk):
    startup, other = _pair(pk)
    return render(
        request,
        "web/duplicate_compare.html",
        {"pair": [_comparison(startup), _comparison(other)], "flagged": startup},
    )


@require_POST
def duplicate_merge(request, pk):
    startup, other = _pair(pk)
    form = MergeForm(request.POST)
    if not form.is_valid() or form.cleaned_data["keep"] not in (startup.pk, other.pk):
        raise Http404("Unknown startup to keep")
    kept, duplicate = (
        (startup, other) if form.cleaned_data["keep"] == startup.pk else (other, startup)
    )
    merge_startups(kept=kept, duplicate=duplicate)
    messages.success(request, "Fusionadas.")
    return redirect("web:startup_detail", pk=kept.pk)


@require_POST
def duplicate_dismiss(request, pk):
    startup = get_object_or_404(Startup, pk=pk)
    dismiss_duplicate(startup)
    messages.info(request, "Marcadas como startups distintas.")
    return redirect("web:duplicate_list")


def _pair(pk):
    startup = get_object_or_404(Startup.objects.select_related("possible_duplicate_of"), pk=pk)
    if startup.possible_duplicate_of is None:
        raise Http404("Not flagged as a possible duplicate")
    return startup, startup.possible_duplicate_of


def _comparison(startup):
    return {
        "startup": startup,
        "domains": list(startup.domains.values_list("domain", flat=True)),
        "source_records": startup.source_records.select_related("source"),
        "contact_count": startup.contacts.count(),
        "analysis_count": startup.analyses.count(),
    }
