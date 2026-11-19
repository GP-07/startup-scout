import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from sources.adapters.hacker_news_hiring import HackerNewsHiringAdapter
from sources.exceptions import SourceFetchError
from startups.constants import ContactRole

FIXTURES_DIR = Path(__file__).parent / "fixtures"
THREADS_FIXTURE = json.loads((FIXTURES_DIR / "hacker_news_hiring_threads.json").read_text())
COMMENTS_FIXTURE = json.loads((FIXTURES_DIR / "hacker_news_hiring_comments.json").read_text())
EMPTY_RESULT = {"hits": [], "nbHits": 0, "page": 0, "nbPages": 0}
NOVEMBER_THREAD_TAGS = "comment,story_8000001"
NEWEST_COMMENT_TIMESTAMP = 1793640000


class RecordingAlgoliaHandler:
    """Serves the fictional threads and November comments, recording every query."""

    def __init__(self, comments=COMMENTS_FIXTURE):
        self.comments = comments
        self.requests_params = []

    def __call__(self, request):
        params = dict(request.url.params)
        self.requests_params.append(params)
        if params.get("tags") == "story,author_whoishiring":
            return httpx.Response(200, json=THREADS_FIXTURE)
        if params.get("tags") == NOVEMBER_THREAD_TAGS:
            return httpx.Response(200, json=self.comments)
        return httpx.Response(200, json=EMPTY_RESULT)

    def comment_requests(self):
        return [params for params in self.requests_params if params["tags"].startswith("comment")]


def failing_algolia_handler(request):
    return httpx.Response(503)


def build_adapter(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return HackerNewsHiringAdapter(http_client=client)


def fetch_by_external_id(handler, cursor=None):
    result = build_adapter(handler).fetch_candidates(cursor or {})
    return {raw_startup.external_id: raw_startup for raw_startup in result.raw_startups}, result


def test_post_header_gives_name_description_and_link_to_the_comment():
    raw_startups, _ = fetch_by_external_id(RecordingAlgoliaHandler())

    lumbre = raw_startups["9100001"]
    assert lumbre.name == "Lumbre Labs"
    assert lumbre.description == "Lumbre Labs (YC W26) | Backend Engineer | Barcelona | REMOTE (EU)"
    assert lumbre.url == "https://news.ycombinator.com/item?id=9100001"
    assert lumbre.published_at == datetime.fromtimestamp(1793635500, tz=UTC)
    assert lumbre.raw_payload["author"] == "fictional_recruiter_1"
    assert "_highlightResult" not in lumbre.raw_payload
    [author] = lumbre.contacts
    assert author.role == ContactRole.OTHER
    assert author.profile_url == "https://news.ycombinator.com/user?id=fictional_recruiter_1"
    assert author.evidence_url == "https://news.ycombinator.com/item?id=9100001"


def test_website_is_the_link_matching_the_company_name_not_the_job_board():
    raw_startups, _ = fetch_by_external_id(RecordingAlgoliaHandler())

    assert raw_startups["9100001"].website == "https://www.lumbrelabs.com/about"


def test_website_falls_back_to_own_link_in_the_header():
    raw_startups, _ = fetch_by_external_id(RecordingAlgoliaHandler())

    assert raw_startups["9100002"].website == "https://qrbt.com"


def test_website_falls_back_to_the_domain_of_a_company_email():
    raw_startups, _ = fetch_by_external_id(RecordingAlgoliaHandler())

    assert raw_startups["9100003"].website == "https://nimbohq.com"


@pytest.mark.parametrize(
    ("external_id", "reason"),
    [
        ("9100004", "only a free email address"),
        ("9100005", "only a job board link"),
        ("9100006", "no company header"),
        ("9100007", "a reply, not a job post"),
        ("9100008", "a deleted comment"),
        ("9100009", "only a link that is neither the company's nor in the header"),
    ],
)
def test_comments_without_a_company_website_are_skipped(external_id, reason):
    raw_startups, _ = fetch_by_external_id(RecordingAlgoliaHandler())

    assert external_id not in raw_startups, reason


def test_first_run_reads_only_the_newest_who_is_hiring_thread():
    handler = RecordingAlgoliaHandler()

    fetch_by_external_id(handler)

    comment_requests = handler.comment_requests()
    assert [params["tags"] for params in comment_requests] == [NOVEMBER_THREAD_TAGS]
    assert "numericFilters" not in comment_requests[0]


def test_later_runs_read_recent_threads_from_cursor_minus_overlap():
    handler = RecordingAlgoliaHandler()

    fetch_by_external_id(handler, cursor={"last_created_at_i": 1793636000})

    comment_requests = handler.comment_requests()
    assert [params["tags"] for params in comment_requests] == [
        NOVEMBER_THREAD_TAGS,
        "comment,story_8000000",
    ]
    assert all(params["numericFilters"] == "created_at_i>1793632400" for params in comment_requests)


def test_threads_are_searched_by_the_whoishiring_account_within_the_recent_window():
    handler = RecordingAlgoliaHandler()

    fetch_by_external_id(handler)

    thread_request = handler.requests_params[0]
    assert thread_request["tags"] == "story,author_whoishiring"
    since_timestamp = int(thread_request["numericFilters"].split(">")[1])
    assert since_timestamp > 0


def test_cursor_moves_to_the_newest_comment_seen():
    _, result = fetch_by_external_id(RecordingAlgoliaHandler())

    assert result.cursor == {"last_created_at_i": NEWEST_COMMENT_TIMESTAMP}


def test_cursor_is_kept_when_there_are_no_new_comments():
    handler = RecordingAlgoliaHandler(comments=EMPTY_RESULT)

    _, result = fetch_by_external_id(handler, cursor={"last_created_at_i": 1793636000})

    assert result.cursor == {"last_created_at_i": 1793636000}


def test_api_errors_raise_source_fetch_error():
    with pytest.raises(SourceFetchError):
        build_adapter(failing_algolia_handler).fetch_candidates({})
