from datetime import date, datetime
from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    date: date
    task_id: str
    equipment_name: str
    magnification: str


class TaskRead(BaseModel):
    id: int
    external_task_id: str
    equipment_id: int
    measured_date: date
    magnification: str
    status: str
    source: str


class EquipmentRead(BaseModel):
    id: int
    name: str
    is_active: bool


class EquipmentCreate(BaseModel):
    name: str
    is_active: bool = True


class IssueCreate(BaseModel):
    equipment_id: int
    start_date: date
    end_date: date
    issue_text: str
    status: str = "open"
    created_by: str | None = None


class IssueUpdate(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    issue_text: str | None = None
    status: str | None = None


class IssueRead(BaseModel):
    id: int
    equipment_id: int
    equipment_name: str
    start_date: date
    end_date: date
    issue_text: str
    status: str
    created_at: datetime


class CalibrationOverrideCreate(BaseModel):
    equipment_id: int
    measured_date: date
    magnification: str
    result_ids: list[int]
    note: str | None = None


class ImageRead(BaseModel):
    id: int
    result_id: int | None
    equipment_id: int
    equipment_name: str
    measured_date: date
    magnification: str
    thumbnail_url: str | None
    original_url: str | None
    error_value: float | None
    distortion_value: float | None
