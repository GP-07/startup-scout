from web.constants import HTMX_REQUEST_HEADER


def is_htmx(request):
    """Whether HTMX made the request, so the view answers with a fragment, not a page."""
    return request.headers.get(HTMX_REQUEST_HEADER) == "true"
