from datetime import date as DateType, datetime
from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class TaskCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    date: DateType = Field(validation_alias=AliasChoices("date", "Date"))
    task_id: str = Field(validation_alias=AliasChoices("task_id", "taskId", "TaskId"))
    equipment_name: str = Field(
        validation_alias=AliasChoices("equipment_name", "facility", "Facility")
    )
    magnification: str = Field(
        validation_alias=AliasChoices("magnification", "magtype", "Magtype", "mag_type")
    )


class TaskRead(BaseModel):
    id: int
    external_task_id: str
    equipment_id: int
    measured_date: DateType
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
    start_date: DateType
    end_date: DateType
    issue_text: str
    status: str = "open"
    created_by: str | None = None


class IssueUpdate(BaseModel):
    start_date: DateType | None = None
    end_date: DateType | None = None
    issue_text: str | None = None
    status: str | None = None


class IssueRead(BaseModel):
    id: int
    equipment_id: int
    equipment_name: str
    start_date: DateType
    end_date: DateType
    issue_text: str
    status: str
    created_at: datetime


class CalibrationOverrideCreate(BaseModel):
    equipment_id: int
    measured_date: DateType
    magnification: str
    result_ids: list[int]
    note: str | None = None


class ImageRead(BaseModel):
    id: int
    result_id: int | None
    equipment_id: int
    equipment_name: str
    measured_date: DateType
    magnification: str
    thumbnail_url: str | None
    original_url: str | None
    error_value: float | None
    distortion_value: float | None
