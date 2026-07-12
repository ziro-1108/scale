"""
Read-only smoke check for the SCALE API.

Run after starting the FastAPI server:

    python -m scripts.smoke_check

This script does not modify data. It checks:
- /api/health is reachable.
- /api/equipments returns registered equipment rows.
- /api/dashboard contains every registered equipment in equipment_status.
- Dashboard rows expose the fields used by the right-side table.
"""

from __future__ import annotations

import json
from urllib.request import urlopen


BASE_URL = "http://127.0.0.1:8000"


def get_json(path: str):
    with urlopen(f"{BASE_URL}{path}", timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    health = get_json("/api/health")
    equipments = get_json("/api/equipments")
    dashboard = get_json("/api/dashboard")

    equipment_ids = {row["id"] for row in equipments}
    dashboard_ids = {row["equipment_id"] for row in dashboard["equipment_status"]}
    missing = equipment_ids - dashboard_ids

    print("Health:", health)
    print("Registered equipments:", len(equipments))
    print("Dashboard equipment rows:", len(dashboard["equipment_status"]))
    print("Missing equipment ids in dashboard:", sorted(missing))

    if missing:
        raise SystemExit("FAIL: Some registered equipments are missing from dashboard.")

    if dashboard["equipment_status"]:
        sample = dashboard["equipment_status"][0]
        required_fields = [
            "equipment_id",
            "equipment_name",
            "high_task_count",
            "middle_task_count",
            "issues",
        ]
        absent = [field for field in required_fields if field not in sample]
        if absent:
            raise SystemExit(f"FAIL: Missing dashboard fields: {absent}")

    print("PASS: SCALE API smoke check completed.")


if __name__ == "__main__":
    main()
