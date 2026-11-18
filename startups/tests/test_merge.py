from sources.constants import SourceKey
from startups.merge import merge_source_data


def test_merge_prefers_higher_priority_source_per_field():
    result = merge_source_data(
        [
            (SourceKey.HACKER_NEWS, {"name": "Acme (HN)", "description": "From HN", "city": ""}),
            (SourceKey.STARTUPXPLORE, {"name": "Acme", "description": "", "city": "Barcelona"}),
        ]
    )

    assert result.values["name"] == "Acme"
    assert result.values["description"] == "From HN"
    assert result.values["city"] == "Barcelona"
    assert result.field_sources == {
        "name": SourceKey.STARTUPXPLORE,
        "description": SourceKey.HACKER_NEWS,
        "city": SourceKey.STARTUPXPLORE,
    }


def test_merge_manual_data_always_wins():
    result = merge_source_data(
        [
            (SourceKey.STARTUPXPLORE, {"name": "Acme", "country": "ES"}),
            (SourceKey.MANUAL, {"name": "Acme Robotics"}),
        ]
    )

    assert result.values["name"] == "Acme Robotics"
    assert result.values["country"] == "ES"


def test_merge_ignores_blank_values():
    result = merge_source_data(
        [
            (SourceKey.MANUAL, {"description": "   "}),
            (SourceKey.HACKER_NEWS, {"description": "Real description"}),
        ]
    )

    assert result.values["description"] == "Real description"


def test_merge_puts_unknown_sources_last():
    result = merge_source_data(
        [
            ("some_future_source", {"name": "Future name"}),
            (SourceKey.HACKER_NEWS, {"name": "HN name"}),
        ]
    )

    assert result.values["name"] == "HN name"


def test_merge_leaves_missing_fields_empty():
    result = merge_source_data([(SourceKey.HACKER_NEWS, {"name": "Acme"})])

    assert result.values["website"] == ""
    assert "website" not in result.field_sources
