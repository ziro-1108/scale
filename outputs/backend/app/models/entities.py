from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from app.db.session import Base


class Equipment(Base):
    __tablename__ = "equipments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), unique=True, nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    tasks = relationship("MeasurementTask", back_populates="equipment")
    results = relationship("MeasurementResult", back_populates="equipment")
    issues = relationship("EquipmentIssue", back_populates="equipment")


class MeasurementTask(Base):
    __tablename__ = "measurement_tasks"

    id = Column(Integer, primary_key=True, index=True)
    external_task_id = Column(String(160), unique=True, nullable=False, index=True)
    equipment_id = Column(Integer, ForeignKey("equipments.id"), nullable=False, index=True)
    measured_date = Column(Date, nullable=False, index=True)
    magnification = Column(String(16), nullable=False, index=True)
    status = Column(String(24), nullable=False, default="queued", index=True)
    source = Column(String(32), nullable=False, default="desktop")
    poll_count = Column(Integer, nullable=False, default=0)
    next_poll_at = Column(DateTime(timezone=True), nullable=True, index=True)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    locked_by = Column(String(80), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    equipment = relationship("Equipment", back_populates="tasks")
    results = relationship("MeasurementResult", back_populates="task")
    images = relationship("MeasurementImage", back_populates="task")


class MeasurementResult(Base):
    __tablename__ = "measurement_results"
    __table_args__ = (
        UniqueConstraint("task_id", "magnification", name="uq_result_task_magnification"),
    )

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("measurement_tasks.id"), nullable=False, index=True)
    equipment_id = Column(Integer, ForeignKey("equipments.id"), nullable=False, index=True)
    measured_date = Column(Date, nullable=False, index=True)
    magnification = Column(String(16), nullable=False, index=True)
    error_value = Column(Float, nullable=False)
    distortion_value = Column(Float, nullable=False)
    is_selected_for_daily_average = Column(Boolean, nullable=False, default=True)
    source = Column(String(32), nullable=False, default="worker")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    task = relationship("MeasurementTask", back_populates="results")
    equipment = relationship("Equipment", back_populates="results")
    images = relationship("MeasurementImage", back_populates="result")


class MeasurementImage(Base):
    __tablename__ = "measurement_images"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("measurement_tasks.id"), nullable=False, index=True)
    result_id = Column(Integer, ForeignKey("measurement_results.id"), nullable=True, index=True)
    equipment_id = Column(Integer, ForeignKey("equipments.id"), nullable=False, index=True)
    measured_date = Column(Date, nullable=False, index=True)
    magnification = Column(String(16), nullable=False, index=True)
    original_image_path = Column(String(500), nullable=True)
    thumbnail_path = Column(String(500), nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    task = relationship("MeasurementTask", back_populates="images")
    result = relationship("MeasurementResult", back_populates="images")


class EquipmentIssue(Base):
    __tablename__ = "equipment_issues"

    id = Column(Integer, primary_key=True, index=True)
    equipment_id = Column(Integer, ForeignKey("equipments.id"), nullable=False, index=True)
    start_date = Column(Date, nullable=False, index=True)
    end_date = Column(Date, nullable=False, index=True)
    issue_text = Column(Text, nullable=False)
    status = Column(String(24), nullable=False, default="open")
    created_by = Column(String(80), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    equipment = relationship("Equipment", back_populates="issues")


class CalibrationOverride(Base):
    __tablename__ = "daily_calibration_overrides"
    __table_args__ = (
        UniqueConstraint(
            "equipment_id",
            "measured_date",
            "magnification",
            name="uq_override_equipment_date_mag",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    equipment_id = Column(Integer, ForeignKey("equipments.id"), nullable=False, index=True)
    measured_date = Column(Date, nullable=False, index=True)
    magnification = Column(String(16), nullable=False, index=True)
    selected_result_ids_json = Column(Text, nullable=False)
    average_error = Column(Float, nullable=False)
    average_distortion = Column(Float, nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
