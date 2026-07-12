"""
Create deterministic demo data for local SCALE validation.

Run from outputs/backend:

    python -m scripts.seed_demo_data

What this script verifies:
- Registered equipments appear in the right-side equipment status table.
- H Mag. / M Mag. show O only when 3 or more tasks exist for that day.
- Issue text appears in the status column when an open issue overlaps the date.
- High and Middle calibration charts have multiple daily average points.

The script only creates equipments whose names start with "DEMO-", so it is easy
to identify demo rows. Do not run this against a production database unless you
intentionally want demo data there.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.db.session import Base, SessionLocal, engine
from app.models.entities import Equipment, EquipmentIssue, MeasurementResult, MeasurementTask


TODAY = date.today()
EQUIPMENT_NAMES = [
    "DEMO-SCALE-A01",
    "DEMO-SCALE-B02",
    "DEMO-SCALE-C03",
    "DEMO-SCALE-D04",
]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_or_create_equipment(db, name: str) -> Equipment:
    equipment = db.query(Equipment).filter(Equipment.name == name).one_or_none()
    if equipment:
        return equipment

    equipment = Equipment(name=name, is_active=True)
    db.add(equipment)
    db.flush()
    return equipment


def create_task_with_optional_result(
    db,
    *,
    equipment: Equipment,
    measured_date: date,
    magnification: str,
    sequence: int,
    create_result: bool,
    error_value: float,
    distortion_value: float,
) -> None:
    """
    Create one measurement task.

    create_result=True simulates "worker already finished this task".
    create_result=False simulates "image/task was registered, but result is not
    ready yet". The dashboard H/M O/X should still be based on task count, not
    result count.
    """

    external_task_id = (
        f"DEMO_{equipment.name}_{measured_date.isoformat()}_{magnification}_{sequence}"
    )
    task = (
        db.query(MeasurementTask)
        .filter(MeasurementTask.external_task_id == external_task_id)
        .one_or_none()
    )
    if not task:
        task = MeasurementTask(
            external_task_id=external_task_id,
            equipment_id=equipment.id,
            measured_date=measured_date,
            magnification=magnification,
            status="succeeded" if create_result else "polling",
            source="demo",
            poll_count=0,
            next_poll_at=utcnow(),
            completed_at=utcnow() if create_result else None,
        )
        db.add(task)
        db.flush()

    if create_result:
        existing = db.query(MeasurementResult).filter(MeasurementResult.task_id == task.id).one_or_none()
        if not existing:
            db.add(
                MeasurementResult(
                    task_id=task.id,
                    equipment_id=equipment.id,
                    measured_date=measured_date,
                    magnification=magnification,
                    error_value=error_value,
                    distortion_value=distortion_value,
                    is_selected_for_daily_average=True,
                    source="demo",
                )
            )


def seed() -> None:
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        equipments = [get_or_create_equipment(db, name) for name in EQUIPMENT_NAMES]

        # 14 days of result data for chart validation.
        for day_offset in range(14):
            measured_date = TODAY - timedelta(days=13 - day_offset)
            drift = (day_offset - 6) / 20

            # A01 has complete High and Middle data every day.
            for mag, base in [("HIGH", 0.05), ("MIDDLE", -0.08)]:
                for seq in range(1, 4):
                    create_task_with_optional_result(
                        db,
                        equipment=equipments[0],
                        measured_date=measured_date,
                        magnification=mag,
                        sequence=seq,
                        create_result=True,
                        error_value=round(base + drift + seq * 0.015, 4),
                        distortion_value=round(0.12 + seq * 0.01, 4),
                    )

        # B02: today has 3 High images/tasks but only 2 Middle images/tasks.
        # Expected right table: H Mag. = O, M Mag. = X.
        for seq in range(1, 4):
            create_task_with_optional_result(
                db,
                equipment=equipments[1],
                measured_date=TODAY,
                magnification="HIGH",
                sequence=seq,
                create_result=True,
                error_value=round(0.18 + seq * 0.02, 4),
                distortion_value=0.16,
            )
        for seq in range(1, 3):
            create_task_with_optional_result(
                db,
                equipment=equipments[1],
                measured_date=TODAY,
                magnification="MIDDLE",
                sequence=seq,
                create_result=False,
                error_value=0,
                distortion_value=0,
            )

        # C03: no images today, but has an open issue over today.
        # Expected right table: H/M = X, status text = the issue text.
        issue = (
            db.query(EquipmentIssue)
            .filter(
                EquipmentIssue.equipment_id == equipments[2].id,
                EquipmentIssue.issue_text == "DEMO 렌즈 점검 중",
            )
            .one_or_none()
        )
        if not issue:
            db.add(
                EquipmentIssue(
                    equipment_id=equipments[2].id,
                    start_date=TODAY,
                    end_date=TODAY + timedelta(days=2),
                    issue_text="DEMO 렌즈 점검 중",
                    status="open",
                    created_by="demo",
                )
            )

        # D04: registered equipment only. It should still appear in the right
        # table even without tasks, results, or issues.
        db.commit()

    print("Demo data seeded.")
    print("Open http://127.0.0.1:5173 and set 점검 기준일 to", TODAY.isoformat())
    print("Expected:")
    print("- DEMO-SCALE-A01: H Mag. O, M Mag. O")
    print("- DEMO-SCALE-B02: H Mag. O, M Mag. X")
    print("- DEMO-SCALE-C03: H Mag. X, M Mag. X, status has issue text")
    print("- DEMO-SCALE-D04: H Mag. X, M Mag. X, blank status")


if __name__ == "__main__":
    seed()
