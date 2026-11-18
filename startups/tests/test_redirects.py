import httpx

from startups.redirects import HttpRedirectResolver


def redirecting_handler(request):
    if request.url.host == "abc.io":
        return httpx.Response(301, headers={"Location": "https://www.abc.com/"})
    return httpx.Response(200)


def head_not_allowed_handler(request):
    if request.method == "HEAD":
        return httpx.Response(405)
    if request.url.host == "abc.io":
        return httpx.Response(302, headers={"Location": "https://abc.com/home"})
    return httpx.Response(200)


def failing_handler(request):
    raise httpx.ConnectError("unreachable", request=request)


def build_resolver(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    return HttpRedirectResolver(client=client)


def test_resolver_follows_redirects_to_final_url():
    resolver = build_resolver(redirecting_handler)

    assert resolver.resolve_final_url("https://abc.io") == "https://www.abc.com/"


def test_resolver_falls_back_to_get_when_head_is_not_allowed():
    resolver = build_resolver(head_not_allowed_handler)

    assert resolver.resolve_final_url("https://abc.io") == "https://abc.com/home"


def test_resolver_returns_none_when_site_is_unreachable():
    resolver = build_resolver(failing_handler)

    assert resolver.resolve_final_url("https://abc.io") is None


def test_resolver_adds_scheme_when_missing():
    resolver = build_resolver(redirecting_handler)

    assert resolver.resolve_final_url("abc.io") == "https://www.abc.com/"
