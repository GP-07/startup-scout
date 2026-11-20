from datetime import datetime, time

from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from startups.analyses import mark_analysis_sent, unmark_analysis_sent
from startups.models import Analysis, Startup
from web.forms import AnalysisForm, MarkSentForm


def analyses_context(startup):
    analyses = startup.analyses.select_related("sent_to")
    return {
        "startup": startup,
        "analyses": [
            {"analysis": analysis, "mark_sent_form": MarkSentForm(startup=startup)}
            for analysis in analyses
        ],
    }


def analysis_create(request, pk):
    startup = get_object_or_404(Startup, pk=pk)
    form = AnalysisForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        analysis = form.save(commit=False)
        analysis.startup = startup
        analysis.save()
        return redirect("web:startup_detail", pk=startup.pk)
    return render(request, "web/analysis_form.html", {"form": form, "startup": startup})


def analysis_edit(request, pk):
    analysis = get_object_or_404(Analysis.objects.select_related("startup"), pk=pk)
    form = AnalysisForm(request.POST or None, instance=analysis)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("web:startup_detail", pk=analysis.startup_id)
    return render(
        request,
        "web/analysis_form.html",
        {"form": form, "startup": analysis.startup, "analysis": analysis},
    )


@require_POST
def analysis_delete(request, pk):
    analysis = get_object_or_404(Analysis.objects.select_related("startup"), pk=pk)
    startup = analysis.startup
    analysis.delete()
    return _render_analyses(request, startup)


@require_POST
def analysis_mark_sent(request, pk):
    analysis = get_object_or_404(Analysis.objects.select_related("startup"), pk=pk)
    form = MarkSentForm(request.POST, startup=analysis.startup)
    if not form.is_valid():
        return _render_analyses(request, analysis.startup, status=400)
    sent_at = timezone.make_aware(datetime.combine(form.cleaned_data["sent_on"], time(12)))
    mark_analysis_sent(analysis, sent_at=sent_at, sent_to=form.cleaned_data["sent_to"])
    response = _render_analyses(request, analysis.startup)
    # The startup may have moved to "contacted": the status and history must refresh too.
    response["HX-Refresh"] = "true"
    return response


@require_POST
def analysis_unmark_sent(request, pk):
    analysis = get_object_or_404(Analysis.objects.select_related("startup"), pk=pk)
    unmark_analysis_sent(analysis)
    return _render_analyses(request, analysis.startup)


def _render_analyses(request, startup, status=200):
    return render(request, "web/partials/analyses.html", analyses_context(startup), status=status)
