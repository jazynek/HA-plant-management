#!/usr/bin/env python3
"""Import the Trello-derived plant seed data into a running Home Assistant instance.

Usage:
    HA_URL=http://homeassistant.local:8123 \\
    HA_TOKEN=eyJhbGciOi... \\
    python3 tools/import_trello_seed.py [path/to/seed.json]

HA_TOKEN must be a Long-Lived Access Token created under your HA profile
(Settings -> your profile -> Security -> Long-lived access tokens).

The script calls the plant_management.import_seed service, which adds a new
plant for each entry not already present (matched by exact `name`), and
updates the existing plant otherwise. Safe to re-run any time you refresh
data/trello_seed.json from Trello (new plants, updated care notes, etc.) —
it will not create duplicates. It does NOT remove plants that disappeared
from the seed file (e.g. ones you deleted from Trello because they died) —
use tools/remove_plants.py for that.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    base_url = os.environ.get("HA_URL")
    token = os.environ.get("HA_TOKEN")
    if not base_url or not token:
        print("Set HA_URL and HA_TOKEN environment variables first.", file=sys.stderr)
        return 1

    seed_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), "..", "data", "trello_seed.json"
    )
    with open(seed_path, encoding="utf-8") as f:
        plants = json.load(f)

    url = base_url.rstrip("/") + "/api/services/plant_management/import_seed"
    body = json.dumps({"plants": plants}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"Imported {len(plants)} plants, HTTP {resp.status}")
    except urllib.error.HTTPError as exc:
        print(f"Import failed: HTTP {exc.code} {exc.reason}\n{exc.read().decode()}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
