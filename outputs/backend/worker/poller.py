import asyncio
import csv
from datetime import timedelta
from io import BytesIO, StringIO
import random
from socket import gethostname
from uuid import uuid4
from zipfile import ZipFile

import httpx
from PIL import Image
from sqlalchemy import or_

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.entities import MeasurementImage, MeasurementResult, MeasurementTask
from app.services.normalizers import utcnow


settings = get_settings()
WORKER_ID = f"{gethostname()}-{uuid4().hex[:8]}"


def fetch_due_tasks() -> list[int]:
    now = utcnow()
    stale_lock_at = now - timedelta(minutes=10)
    with SessionLocal() as db:
        tasks = (
            db.query(MeasurementTask)
            .filter(
                MeasurementTask.status.in_(["queued", "polling"]),
                MeasurementTask.next_poll_at <= now,
                or_(MeasurementTask.locked_at.is_(None), MeasurementTask.locked_at < stale_lock_at),
            )
            .order_by(MeasurementTask.next_poll_at)
            .limit(settings.worker_batch_size)
            .all()
        )
        ids = [task.id for task in tasks]
        for task in tasks:
            task.locked_at = now
            task.locked_by = WORKER_ID
            task.status = "polling"
        db.commit()
        return ids


def parse_result_zip(content: bytes) -> tuple[float, float]:
    with ZipFile(BytesIO(content)) as archive:
        csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if not csv_names:
            raise ValueError("result zip does not contain a CSV file")
        csv_text = archive.read(csv_names[0]).decode("utf-8-sig")

    reader = csv.DictReader(StringIO(csv_text))
    row = next(reader, None)
    if not row:
        raise ValueError("result CSV is empty")

    lower_row = {key.lower().strip(): value for key, value in row.items() if key}
    return float(lower_row["error"]), float(lower_row["distortion"])


def create_thumbnail(original_path: str) -> tuple[str, int, int]:
    source = settings.storage_dir / original_path
    thumbnail_name = f"{source.stem}_thumb.jpg"
    thumbnail_path = settings.thumbnails_dir / thumbnail_name
    with Image.open(source) as image:
        image = image.convert("RGB")
        width, height = image.size
        image.thumbnail((256, 256))
        canvas = Image.new("RGB", (256, 256), "white")
        left = (256 - image.width) // 2
        top = (256 - image.height) // 2
        canvas.paste(image, (left, top))
        canvas.save(thumbnail_path, "JPEG", quality=88)
    return f"thumbnails/{thumbnail_name}", width, height


def save_image_bytes(task: MeasurementTask, image_bytes: bytes) -> str:
    filename = f"{task.external_task_id}_{uuid4().hex[:8]}.jpg"
    target = settings.uploads_dir / filename
    target.write_bytes(image_bytes)
    return f"uploads/{filename}"


def save_success(task_id: int, error_value: float, distortion_value: float, image_path: str | None) -> None:
    with SessionLocal() as db:
        task = db.get(MeasurementTask, task_id)
        if not task:
            return

        existing = (
            db.query(MeasurementResult)
            .filter(
                MeasurementResult.task_id == task.id,
                MeasurementResult.magnification == task.magnification,
            )
            .one_or_none()
        )
        if existing:
            task.status = "succeeded"
            task.completed_at = utcnow()
            task.locked_at = None
            task.locked_by = None
            db.commit()
            return

        result = MeasurementResult(
            task_id=task.id,
            equipment_id=task.equipment_id,
            measured_date=task.measured_date,
            magnification=task.magnification,
            error_value=error_value,
            distortion_value=distortion_value,
            source=task.source,
            is_selected_for_daily_average=True,
        )
        db.add(result)
        db.flush()

        images = db.query(MeasurementImage).filter(MeasurementImage.task_id == task.id).all()
        if image_path and not images:
            images = [
                MeasurementImage(
                    task_id=task.id,
                    equipment_id=task.equipment_id,
                    measured_date=task.measured_date,
                    magnification=task.magnification,
                    original_image_path=image_path,
                )
            ]
            db.add_all(images)
            db.flush()

        for image in images:
            image.result_id = result.id
            if not image.original_image_path and image_path:
                image.original_image_path = image_path
            if image.original_image_path and not image.thumbnail_path:
                try:
                    thumb, width, height = create_thumbnail(image.original_image_path)
                    image.thumbnail_path = thumb
                    image.width = width
                    image.height = height
                except Exception as exc:
                    task.last_error = f"thumbnail failed: {exc}"

        task.status = "succeeded"
        task.completed_at = utcnow()
        task.locked_at = None
        task.locked_by = None
        db.commit()


def reschedule(task_id: int, error: str | None = None) -> None:
    with SessionLocal() as db:
        task = db.get(MeasurementTask, task_id)
        if not task:
            return
        task.poll_count += 1
        delay_seconds = min(300, 5 * max(1, task.poll_count))
        task.next_poll_at = utcnow() + timedelta(seconds=delay_seconds)
        task.status = "polling"
        task.locked_at = None
        task.locked_by = None
        if error:
            task.last_error = error[:2000]
        if task.poll_count >= 120:
            task.status = "failed"
        db.commit()


async def process_mock_task(task_id: int) -> None:
    with SessionLocal() as db:
        task = db.get(MeasurementTask, task_id)
        if not task:
            return
        seed = f"{task.external_task_id}:{task.equipment_id}:{task.measured_date}:{task.magnification}"
        random.seed(seed)
        error_value = round(random.uniform(-0.8, 0.8), 4)
        distortion_value = round(random.uniform(0.02, 0.32), 4)
    save_success(task_id, error_value, distortion_value, None)


async def process_external_task(client: httpx.AsyncClient, task_id: int) -> None:
    with SessionLocal() as db:
        task = db.get(MeasurementTask, task_id)
        if not task:
            return
        external_task_id = task.external_task_id

    if external_task_id.startswith("MOCK_"):
        await process_mock_task(task_id)
        return

    result_url = settings.measurement_result_url.format(task_id=external_task_id)
    image_url = settings.measurement_image_url.format(task_id=external_task_id)

    try:
        response = await client.get(result_url)
        if response.status_code in {202, 204, 404}:
            reschedule(task_id)
            return
        response.raise_for_status()
        error_value, distortion_value = parse_result_zip(response.content)

        image_path = None
        image_response = await client.get(image_url)
        if image_response.status_code == 200 and image_response.content:
            with SessionLocal() as db:
                task = db.get(MeasurementTask, task_id)
                if task:
                    image_path = save_image_bytes(task, image_response.content)

        save_success(task_id, error_value, distortion_value, image_path)
    except ValueError as exc:
        with SessionLocal() as db:
            task = db.get(MeasurementTask, task_id)
            if task:
                task.status = "failed"
                task.last_error = str(exc)
                task.locked_at = None
                task.locked_by = None
                db.commit()
    except Exception as exc:
        reschedule(task_id, str(exc))


async def run_forever() -> None:
    semaphore = asyncio.Semaphore(settings.worker_concurrency)
    timeout = httpx.Timeout(30.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        while True:
            task_ids = fetch_due_tasks()
            if not task_ids:
                await asyncio.sleep(settings.worker_poll_interval_seconds)
                continue

            async def guarded(task_id: int) -> None:
                async with semaphore:
                    await process_external_task(client, task_id)

            await asyncio.gather(*(guarded(task_id) for task_id in task_ids))


if __name__ == "__main__":
    asyncio.run(run_forever())
