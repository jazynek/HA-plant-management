#!/usr/bin/env python3
"""Remove one or more plants from Home Assistant by their exact name.

Usage:
    HA_URL=http://homeassistant.local:8123 \\
    HA_TOKEN=eyJhbGciOi... \\
    python3 tools/remove_plants.py "17. Tillandsia caput-medusae" "18. Tillandsia ionantha"

Use this after deleting dead/gone plants from the Trello board and
data/trello_seed.json, to also remove them (and their entities) from Home
Assistant. Names must match exactly what's stored in the `name` field
(same as shown in the plant's device name in HA).
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

    names = sys.argv[1:]
    if not names:
        print("Pass one or more exact plant names as arguments.", file=sys.stderr)
        return 1

    url = base_url.rstrip("/") + "/api/services/plant_management/remove_by_name"
    ok = True
    for name in names:
        body = json.dumps({"name": name}).encode("utf-8")
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
                print(f"Removed '{name}' (HTTP {resp.status})")
        except urllib.error.HTTPError as exc:
            print(f"Failed to remove '{name}': HTTP {exc.code} {exc.reason}", file=sys.stderr)
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
