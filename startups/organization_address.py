"""Reads the address a company publishes as schema.org data on its home page.

Pure functions: no network and no database. It is evidence of where the startup is established
(startups/headquarters.py).
"""

import json

from bs4 import BeautifulSoup

from startups.constants import (
    JSON_LD_ORGANIZATION_TYPES,
    JSON_LD_SCRIPT_TYPE,
    LOCATION_EVIDENCE_MAX_LENGTH,
    ORGANIZATION_ADDRESS_FIELDS,
)


def organization_location(html):
    """ "Locality, region, country" of the first organization with an address, or blank."""
    soup = BeautifulSoup(html or "", "html.parser")
    for script in soup.find_all("script", type=JSON_LD_SCRIPT_TYPE):
        try:
            data = json.loads(script.get_text())
        except ValueError:
            continue
        for organization in _walk_organizations(data):
            location = _address_text(organization.get("address"))
            if location:
                return location[:LOCATION_EVIDENCE_MAX_LENGTH]
    return ""


def _walk_organizations(node):
    if isinstance(node, list):
        for item in node:
            yield from _walk_organizations(item)
        return
    if not isinstance(node, dict):
        return
    node_types = node.get("@type")
    node_types = node_types if isinstance(node_types, list) else [node_types]
    if JSON_LD_ORGANIZATION_TYPES.intersection(str(node_type) for node_type in node_types):
        yield node
    for value in node.values():
        if isinstance(value, dict | list):
            yield from _walk_organizations(value)


def _address_text(address):
    if isinstance(address, list):
        return next((text for text in map(_address_text, address) if text), "")
    if isinstance(address, str):
        return " ".join(address.split())
    if not isinstance(address, dict):
        return ""
    parts = []
    for field in ORGANIZATION_ADDRESS_FIELDS:
        value = address.get(field)
        if isinstance(value, dict):
            value = value.get("name")
        if isinstance(value, str) and value.strip():
            parts.append(" ".join(value.split()))
    return ", ".join(parts)
