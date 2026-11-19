import json
from pathlib import Path

import httpx
import pytest

from sources.adapters.hacker_news import HackerNewsAdapter
from sources.exceptions import SourceFetchError

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SHOW_HN_FIXTURE = json.loads((FIXTURES_DIR / "hacker_news_show_hn.json").read_text())
LAUNCH_HN_FIXTURE = json.loads((FIXTURES_DIR / "hacker_news_launch_hn.json").read_text())


class RecordingAlgoliaHandler:
    """Answers Algolia requests with the fixtures and remembers the query parameters."""

    def __init__(self):
        self.requests_params = []

    def __call__(self, request):
        params = dict(request.url.params)
        self.requests_params.append(params)
        if params.get("tags") == "show_hn":
            return httpx.Response(200, json=SHOW_HN_FIXTURE)
        return httpx.Response(200, json=LAUNCH_HN_FIXTURE)


def failing_algolia_handler(request):
    return httpx.Response(503)


def build_adapter(handler, tags=("show_hn", "launch_hn")):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return HackerNewsAdapter(config={"tags": list(tags)}, http_client=client)


def fetch_by_external_id(adapter, cursor=None):
    result = adapter.fetch_candidates(cursor or {"last_created_at_i": 1795000000})
    return {raw_startup.external_id: raw_startup for raw_startup in result.raw_startups}, result


def test_show_hn_post_uses_post_url_as_website_and_title_as_name():
    raw_startups, _ = fetch_by_external_id(build_adapter(RecordingAlgoliaHandler()))

    lumbre = raw_startups["9000001"]
    assert lumbre.name == "Lumbre"
    assert lumbre.website == "https://www.lumbreinvoices.com/?ref=hn"
    assert lumbre.description == "Invoices that chase late payers for you"
    assert lumbre.url == "https://news.ycombinator.com/item?id=9000001"
    assert "_highlightResult" not in lumbre.raw_payload
    assert lumbre.raw_payload["author"] == "fictional_founder_1"


def test_repository_link_is_replaced_by_own_domain_found_in_post_text():
    raw_startups, _ = fetch_by_external_id(build_adapter(RecordingAlgoliaHandler()))

    brisa = raw_startups["9000002"]
    assert brisa.name == "Brisa"
    assert brisa.website == "https://brisaflags.com/docs"
    assert brisa.description == "a self-hosted feature flag server"


def test_post_without_own_domain_keeps_repository_link():
    raw_startups, _ = fetch_by_external_id(build_adapter(RecordingAlgoliaHandler()))

    assert raw_startups["9000003"].website == "https://github.com/someone/tiny-dates"
    assert raw_startups["9000003"].name == "A tiny Rust crate to parse dates"


def test_launch_hn_post_takes_website_from_text_and_drops_batch_from_name():
    raw_startups, _ = fetch_by_external_id(build_adapter(RecordingAlgoliaHandler()))

    vela = raw_startups["9000010"]
    assert vela.name == "Vela"
    assert vela.website == "https://velawarehouse.com"
    assert vela.description == "Copilot for warehouse operators"


def test_stories_that_only_mention_launch_hn_are_ignored():
    raw_startups, _ = fetch_by_external_id(build_adapter(RecordingAlgoliaHandler()))

    assert "9000011" not in raw_startups


def test_cursor_moves_to_newest_post_seen():
    _, result = fetch_by_external_id(build_adapter(RecordingAlgoliaHandler()))

    assert result.cursor == {"last_created_at_i": 1795089600}


def test_requests_posts_newer_than_cursor_minus_overlap_for_each_configured_tag():
    handler = RecordingAlgoliaHandler()

    fetch_by_external_id(build_adapter(handler), cursor={"last_created_at_i": 1795000000})

    assert [params.get("tags") for params in handler.requests_params] == ["show_hn", "story"]
    assert all(
        params["numericFilters"] == "created_at_i>1794996400" for params in handler.requests_params
    )
    assert handler.requests_params[1]["query"] == '"Launch HN"'


def test_without_cursor_starts_from_initial_lookback_window():
    handler = RecordingAlgoliaHandler()
    adapter = build_adapter(handler, tags=("show_hn",))

    adapter.fetch_candidates({})

    since_timestamp = int(handler.requests_params[0]["numericFilters"].split(">")[1])
    assert since_timestamp > 0


def test_unknown_tag_in_config_is_rejected():
    adapter = build_adapter(RecordingAlgoliaHandler(), tags=("ask_hn",))

    with pytest.raises(SourceFetchError):
        adapter.fetch_candidates({})


def test_api_errors_raise_source_fetch_error():
    adapter = build_adapter(failing_algolia_handler)

    with pytest.raises(SourceFetchError):
        adapter.fetch_candidates({})
