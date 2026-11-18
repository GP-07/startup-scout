from dataclasses import dataclass

from startups.constants import MERGEABLE_FIELDS, SOURCE_MERGE_PRIORITY
from startups.domains import normalize_name


@dataclass(frozen=True)
class MergeResult:
    values: dict
    field_sources: dict


def merge_source_data(records):
    """Merge `(source_key, data)` pairs per field: the highest-priority non-blank value wins."""
    ordered_records = sorted(records, key=_priority_of)
    values = {}
    field_sources = {}
    for field_name in MERGEABLE_FIELDS:
        values[field_name] = ""
        for source_key, data in ordered_records:
            value = str(data.get(field_name) or "").strip()
            if value:
                values[field_name] = value
                field_sources[field_name] = str(source_key)
                break
    return MergeResult(values=values, field_sources=field_sources)


def recompute_startup(startup):
    """Rebuild the startup's fields from all of its source records. Deterministic and idempotent."""
    records = startup.source_records.select_related("source").order_by("id")
    result = merge_source_data((record.source.key, record.data) for record in records)
    for field_name, value in result.values.items():
        if field_name == "name" and not value:
            continue
        setattr(startup, field_name, value)
    startup.normalized_name = normalize_name(startup.name)
    startup.field_sources = result.field_sources
    startup.save()
    return startup


def _priority_of(record):
    source_key = record[0]
    if source_key in SOURCE_MERGE_PRIORITY:
        return SOURCE_MERGE_PRIORITY.index(source_key)
    return len(SOURCE_MERGE_PRIORITY)
