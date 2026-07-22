"""
Insert custom equipment calibration test data into the configured MySQL DB.

Run from outputs/backend:

    python -m scripts.seed_custom_equipment_data --equipment EQP-TEST-01 EQP-TEST-02

Useful options:

    python -m scripts.seed_custom_equipment_data ^
      --equipment LINE-A-01 LINE-B-02 ^
      --date 2026-07-23 ^
      --days 7 ^
      --high-count 3 ^
      --middle-count 3

This script creates:
- equipments rows for the requested equipment names
- measurement_tasks rows for each date / equipment / magnification
- measurement_results rows connected to those tasks

It prints each measurement_results row before insert, so the frontend chart and
right-side status table can be checked against the DB input.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone

from app.db.session import Base, SessionLocal, engine
from app.models.entities import Equipment, MeasurementResult, MeasurementTask


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed custom SCALE equipment test rows into MySQL."
    )
    parser.add_argument(
        "--equipment",
        nargs="+",
        default=["TEST-SCALE-X01", "TEST-SCALE-X02"],
        help="Equipment names to insert. Example: --equipment EQP-A01 EQP-B02",
    )
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="Last measured date to insert. Default: today. Format: YYYY-MM-DD",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=14,
        help="Number of days ending at --date. Default: 14",
    )
    parser.add_argument(
        "--high-count",
        type=int,
        default=3,
        help="Number of High magnification rows per equipment/date. Default: 3",
    )
    parser.add_argument(
        "--middle-count",
        type=int,
        default=3,
        help="Number of Middle magnification rows per equipment/date. Default: 3",
    )
    parser.add_argument(
        "--prefix",
        default="CUSTOM",
        help="Prefix for external task IDs. Default: CUSTOM",
    )
    return parser.parse_args()


def get_or_create_equipment(db, name: str) -> Equipment:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("equipment name must not be empty")

    equipment = db.query(Equipment).filter(Equipment.name == clean_name).one_or_none()
    if equipment:
        return equipment

    equipment = Equipment(name=clean_name, is_active=True)
    db.add(equipment)
    db.flush()
    return equipment


def make_error_value(equipment_index: int, day_index: int, sequence: int, magnification: str) -> float:
    base = 0.08 if magnification == "HIGH" else -0.06
    equipment_offset = equipment_index * 0.11
    day_drift = (day_index - 6) * 0.025
    sequence_offset = sequence * 0.012
    return round(base + equipment_offset + day_drift + sequence_offset, 4)


def make_distortion_value(equipment_index: int, sequence: int, magnification: str) -> float:
    base = 0.12 if magnification == "HIGH" else 0.09
    return round(base + equipment_index * 0.015 + sequence * 0.006, 4)


def create_task_and_result(
    db,
    *,
    equipment: Equipment,
    equipment_index: int,
    measured_date: date,
    day_index: int,
    magnification: str,
    sequence: int,
    prefix: str,
) -> bool:
    external_task_id = (
        f"{prefix}_{equipment.name}_{measured_date.isoformat()}_{magnification}_{sequence}"
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
            status="succeeded",
            source="custom_seed",
            poll_count=0,
            next_poll_at=utcnow(),
            completed_at=utcnow(),
        )
        db.add(task)
        db.flush()

    existing_result = (
        db.query(MeasurementResult).filter(MeasurementResult.task_id == task.id).one_or_none()
    )
    if existing_result:
        return False

    result_row = {
        "task_id": task.id,
        "external_task_id": task.external_task_id,
        "equipment_id": equipment.id,
        "equipment_name": equipment.name,
        "measured_date": measured_date,
        "magnification": magnification,
        "error_value": make_error_value(
            equipment_index, day_index, sequence, magnification
        ),
        "distortion_value": make_distortion_value(equipment_index, sequence, magnification),
        "is_selected_for_daily_average": True,
        "source": "custom_seed",
    }
    print(json.dumps(result_row, ensure_ascii=False, default=str))
    db.add(
        MeasurementResult(
            task_id=result_row["task_id"],
            equipment_id=result_row["equipment_id"],
            measured_date=result_row["measured_date"],
            magnification=result_row["magnification"],
            error_value=result_row["error_value"],
            distortion_value=result_row["distortion_value"],
            is_selected_for_daily_average=result_row["is_selected_for_daily_average"],
            source=result_row["source"],
        )
    )
    return True


def seed() -> None:
    args = parse_args()
    end_date = date.fromisoformat(args.date)
    if args.days < 1:
        raise ValueError("--days must be 1 or greater")

    Base.metadata.create_all(bind=engine)
    inserted_results = 0

    print("measurement_results rows to insert:")
    with SessionLocal() as db:
        equipments = [get_or_create_equipment(db, name) for name in args.equipment]
        for day_index in range(args.days):
            measured_date = end_date - timedelta(days=args.days - 1 - day_index)
            for equipment_index, equipment in enumerate(equipments):
                for magnification, count in (
                    ("HIGH", args.high_count),
                    ("MIDDLE", args.middle_count),
                ):
                    for sequence in range(1, count + 1):
                        inserted = create_task_and_result(
                            db,
                            equipment=equipment,
                            equipment_index=equipment_index,
                            measured_date=measured_date,
                            day_index=day_index,
                            magnification=magnification,
                            sequence=sequence,
                            prefix=args.prefix,
                        )
                        if inserted:
                            inserted_results += 1
        db.commit()

    print(
        json.dumps(
            {
                "seed_complete": True,
                "date_from": (end_date - timedelta(days=args.days - 1)).isoformat(),
                "date_to": end_date.isoformat(),
                "equipment_names": args.equipment,
                "inserted_results": inserted_results,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    seed()
