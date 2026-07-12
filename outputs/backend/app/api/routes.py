from datetime import date, timedelta
import json
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import (
    CalibrationOverride,
    Equipment,
    EquipmentIssue,
    MeasurementImage,
    MeasurementResult,
    MeasurementTask,
)
from app.schemas.api import (
    CalibrationOverrideCreate,
    EquipmentCreate,
    IssueCreate,
    IssueRead,
    IssueUpdate,
    TaskCreate,
)
from app.services.normalizers import normalize_magnification, utcnow


router = APIRouter(prefix="/api")


def get_or_create_equipment(db: Session, name: str) -> Equipment:
    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="equipment_name is required")

    equipment = db.query(Equipment).filter(Equipment.name == clean_name).one_or_none()
    if equipment:
        return equipment

    equipment = Equipment(name=clean_name, is_active=True)
    db.add(equipment)
    db.flush()
    return equipment


def file_url(path: str | None) -> str | None:
    if not path:
        return None
    return f"/storage/{Path(path).as_posix()}"


@router.get("/health")
def health():
    return {"ok": True, "service": "SCALE"}


@router.get("/equipments")
def list_equipments(db: Session = Depends(get_db)):
    rows = db.query(Equipment).order_by(Equipment.name).all()
    return [{"id": row.id, "name": row.name, "is_active": row.is_active} for row in rows]


@router.post("/equipments")
def create_equipment(payload: EquipmentCreate, db: Session = Depends(get_db)):
    equipment = get_or_create_equipment(db, payload.name)
    equipment.is_active = payload.is_active
    db.commit()
    db.refresh(equipment)
    return {"id": equipment.id, "name": equipment.name, "is_active": equipment.is_active}


@router.post("/tasks")
def create_task(payload: TaskCreate, db: Session = Depends(get_db)):
    try:
        magnification = normalize_magnification(payload.magnification)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    existing = (
        db.query(MeasurementTask)
        .filter(MeasurementTask.external_task_id == payload.task_id)
        .one_or_none()
    )
    if existing:
        return {
            "id": existing.id,
            "external_task_id": existing.external_task_id,
            "status": existing.status,
            "already_exists": True,
        }

    equipment = get_or_create_equipment(db, payload.equipment_name)
    task = MeasurementTask(
        external_task_id=payload.task_id,
        equipment_id=equipment.id,
        measured_date=payload.date,
        magnification=magnification,
        status="queued",
        source="desktop",
        next_poll_at=utcnow(),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return {
        "id": task.id,
        "external_task_id": task.external_task_id,
        "status": task.status,
        "already_exists": False,
    }


@router.get("/dashboard")
def dashboard(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    status_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    today = date.today()
    end = end_date or today
    start = start_date or (end - timedelta(days=13))
    check_date = status_date or end

    result_rows = (
        db.query(
            MeasurementResult.measured_date,
            MeasurementResult.magnification,
            func.avg(MeasurementResult.error_value),
            func.avg(MeasurementResult.distortion_value),
            func.count(MeasurementResult.id),
            func.sum(func.abs(MeasurementResult.error_value) > 1.0),
        )
        .filter(
            MeasurementResult.measured_date.between(start, end),
            MeasurementResult.is_selected_for_daily_average.is_(True),
        )
        .group_by(MeasurementResult.measured_date, MeasurementResult.magnification)
        .all()
    )

    trend_by_date: dict[date, dict] = {
        start + timedelta(days=offset): {
            "date": (start + timedelta(days=offset)).isoformat(),
            "high_avg_error": None,
            "middle_avg_error": None,
            "high_avg_distortion": None,
            "middle_avg_distortion": None,
            "high_count": 0,
            "middle_count": 0,
            "outlier_count": 0,
        }
        for offset in range((end - start).days + 1)
    }

    for row_date, mag, avg_error, avg_distortion, count, outliers in result_rows:
        key = "high" if mag == "HIGH" else "middle"
        item = trend_by_date[row_date]
        item[f"{key}_avg_error"] = round(float(avg_error), 4) if avg_error is not None else None
        item[f"{key}_avg_distortion"] = (
            round(float(avg_distortion), 4) if avg_distortion is not None else None
        )
        item[f"{key}_count"] = int(count or 0)
        item["outlier_count"] += int(outliers or 0)

    equipments = db.query(Equipment).order_by(Equipment.name).all()
    result_count_rows = (
        db.query(
            MeasurementResult.equipment_id,
            MeasurementResult.magnification,
            func.count(MeasurementResult.id),
        )
        .filter(
            MeasurementResult.measured_date == check_date,
            MeasurementResult.is_selected_for_daily_average.is_(True),
        )
        .group_by(MeasurementResult.equipment_id, MeasurementResult.magnification)
        .all()
    )
    result_counts: dict[tuple[int, str], int] = {
        (equipment_id, mag): int(count) for equipment_id, mag, count in result_count_rows
    }

    task_count_rows = (
        db.query(
            MeasurementTask.equipment_id,
            MeasurementTask.magnification,
            func.count(MeasurementTask.id),
        )
        .filter(MeasurementTask.measured_date == check_date)
        .group_by(MeasurementTask.equipment_id, MeasurementTask.magnification)
        .all()
    )
    task_counts: dict[tuple[int, str], int] = {
        (equipment_id, mag): int(count) for equipment_id, mag, count in task_count_rows
    }

    issue_rows = (
        db.query(EquipmentIssue)
        .filter(
            EquipmentIssue.start_date <= check_date,
            EquipmentIssue.end_date >= check_date,
            EquipmentIssue.status == "open",
        )
        .all()
    )
    issues_by_equipment: dict[int, list[EquipmentIssue]] = {}
    for issue in issue_rows:
        issues_by_equipment.setdefault(issue.equipment_id, []).append(issue)

    equipment_status = []
    for equipment in equipments:
        high_count = result_counts.get((equipment.id, "HIGH"), 0)
        middle_count = result_counts.get((equipment.id, "MIDDLE"), 0)
        high_task_count = task_counts.get((equipment.id, "HIGH"), 0)
        middle_task_count = task_counts.get((equipment.id, "MIDDLE"), 0)
        active_issues = issues_by_equipment.get(equipment.id, [])
        completed = high_count >= 3 and middle_count >= 3
        image_registered = high_task_count > 0 or middle_task_count > 0
        equipment_status.append(
            {
                "equipment_id": equipment.id,
                "equipment_name": equipment.name,
                "high_count": high_count,
                "middle_count": middle_count,
                "high_task_count": high_task_count,
                "middle_task_count": middle_task_count,
                "image_registered": image_registered,
                "completed": completed,
                "status": "issue"
                if active_issues
                else ("completed" if completed else ("registered" if image_registered else "pending")),
                "issues": [
                    {
                        "id": issue.id,
                        "start_date": issue.start_date.isoformat(),
                        "end_date": issue.end_date.isoformat(),
                        "issue_text": issue.issue_text,
                    }
                    for issue in active_issues
                ],
            }
        )

    return {
        "range": {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "status_date": check_date.isoformat(),
        },
        "trend": list(trend_by_date.values()),
        "equipment_status": equipment_status,
    }


@router.post("/issues")
def create_issue(payload: IssueCreate, db: Session = Depends(get_db)):
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="end_date must be after start_date")
    equipment = db.get(Equipment, payload.equipment_id)
    if not equipment:
        raise HTTPException(status_code=404, detail="equipment not found")

    issue = EquipmentIssue(**payload.model_dump())
    db.add(issue)
    db.commit()
    db.refresh(issue)
    return issue_response(issue, equipment)


@router.get("/issues", response_model=list[IssueRead])
def list_issues(
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(EquipmentIssue).join(Equipment)
    if start_date and end_date:
        query = query.filter(
            EquipmentIssue.start_date <= end_date,
            EquipmentIssue.end_date >= start_date,
        )
    rows = query.order_by(EquipmentIssue.start_date.desc()).all()
    return [issue_response(row, row.equipment) for row in rows]


@router.put("/issues/{issue_id}")
def update_issue(issue_id: int, payload: IssueUpdate, db: Session = Depends(get_db)):
    issue = db.get(EquipmentIssue, issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="issue not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(issue, key, value)
    if issue.end_date < issue.start_date:
        raise HTTPException(status_code=400, detail="end_date must be after start_date")
    db.commit()
    db.refresh(issue)
    return issue_response(issue, issue.equipment)


def issue_response(issue: EquipmentIssue, equipment: Equipment) -> dict:
    return {
        "id": issue.id,
        "equipment_id": issue.equipment_id,
        "equipment_name": equipment.name,
        "start_date": issue.start_date,
        "end_date": issue.end_date,
        "issue_text": issue.issue_text,
        "status": issue.status,
        "created_at": issue.created_at,
    }


@router.post("/upload/mock")
async def mock_upload(
    equipment_id: int = Form(...),
    measured_date: date = Form(...),
    magnification: str = Form(...),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    try:
        normalized_mag = normalize_magnification(magnification)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    equipment = db.get(Equipment, equipment_id)
    if not equipment:
        raise HTTPException(status_code=404, detail="equipment not found")

    settings = get_settings()
    created = []
    for upload in files:
        suffix = Path(upload.filename or "upload.jpg").suffix or ".jpg"
        storage_name = f"{uuid4().hex}{suffix}"
        storage_path = settings.uploads_dir / storage_name
        with storage_path.open("wb") as target:
            shutil.copyfileobj(upload.file, target)

        task = MeasurementTask(
            external_task_id=f"MOCK_{uuid4().hex}",
            equipment_id=equipment.id,
            measured_date=measured_date,
            magnification=normalized_mag,
            status="queued",
            source="web_upload",
            next_poll_at=utcnow(),
        )
        db.add(task)
        db.flush()
        image = MeasurementImage(
            task_id=task.id,
            equipment_id=equipment.id,
            measured_date=measured_date,
            magnification=normalized_mag,
            original_image_path=f"uploads/{storage_name}",
        )
        db.add(image)
        created.append({"task_id": task.external_task_id, "filename": upload.filename})

    db.commit()
    return {"created": created}


@router.get("/images")
def list_images(
    measured_date: date = Query(..., alias="date"),
    equipment_id: int = Query(...),
    magnification: str = Query(...),
    db: Session = Depends(get_db),
):
    try:
        normalized_mag = normalize_magnification(magnification)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    rows = (
        db.query(MeasurementImage, MeasurementResult, Equipment)
        .join(Equipment, Equipment.id == MeasurementImage.equipment_id)
        .outerjoin(MeasurementResult, MeasurementResult.id == MeasurementImage.result_id)
        .filter(
            MeasurementImage.measured_date == measured_date,
            MeasurementImage.equipment_id == equipment_id,
            MeasurementImage.magnification == normalized_mag,
        )
        .order_by(MeasurementImage.created_at.desc())
        .all()
    )
    return [
        {
            "id": image.id,
            "result_id": image.result_id,
            "equipment_id": image.equipment_id,
            "equipment_name": equipment.name,
            "measured_date": image.measured_date.isoformat(),
            "magnification": image.magnification,
            "thumbnail_url": file_url(image.thumbnail_path),
            "original_url": file_url(image.original_image_path),
            "error_value": result.error_value if result else None,
            "distortion_value": result.distortion_value if result else None,
        }
        for image, result, equipment in rows
    ]


@router.post("/calibration-overrides")
def create_calibration_override(
    payload: CalibrationOverrideCreate,
    db: Session = Depends(get_db),
):
    try:
        normalized_mag = normalize_magnification(payload.magnification)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    results = (
        db.query(MeasurementResult)
        .filter(
            MeasurementResult.id.in_(payload.result_ids),
            MeasurementResult.equipment_id == payload.equipment_id,
            MeasurementResult.measured_date == payload.measured_date,
            MeasurementResult.magnification == normalized_mag,
        )
        .all()
    )
    if not results:
        raise HTTPException(status_code=400, detail="no matching results selected")

    average_error = sum(row.error_value for row in results) / len(results)
    average_distortion = sum(row.distortion_value for row in results) / len(results)
    existing = (
        db.query(CalibrationOverride)
        .filter(
            CalibrationOverride.equipment_id == payload.equipment_id,
            CalibrationOverride.measured_date == payload.measured_date,
            CalibrationOverride.magnification == normalized_mag,
        )
        .one_or_none()
    )
    data = {
        "selected_result_ids_json": json.dumps(payload.result_ids),
        "average_error": average_error,
        "average_distortion": average_distortion,
        "note": payload.note,
    }
    if existing:
        for key, value in data.items():
            setattr(existing, key, value)
        override = existing
    else:
        override = CalibrationOverride(
            equipment_id=payload.equipment_id,
            measured_date=payload.measured_date,
            magnification=normalized_mag,
            **data,
        )
        db.add(override)

    db.commit()
    db.refresh(override)
    return {
        "id": override.id,
        "average_error": round(override.average_error, 4),
        "average_distortion": round(override.average_distortion, 4),
        "selected_count": len(results),
    }
