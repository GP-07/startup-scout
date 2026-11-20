from django.shortcuts import render

from sources.models import Source
from web.constants import RUNS_PER_SOURCE


def run_list(request):
    sources = [
        {"source": source, "runs": source.runs.all()[:RUNS_PER_SOURCE]}
        for source in Source.objects.order_by("name")
    ]
    return render(request, "web/run_list.html", {"sources": sources})
