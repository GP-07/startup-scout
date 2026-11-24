from django.shortcuts import render

from web.rules import business_rules


def rule_list(request):
    """The business rules that filter startups and openings, read-only."""
    return render(request, "web/rule_list.html", {"sections": business_rules()})
