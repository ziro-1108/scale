# SCALE

SCALE is a FastAPI + SQLAlchemy backend, a long-running polling worker, and a Vite + Vue3 frontend for equipment calibration monitoring.

The database is expected to be a company-provided Cloud MySQL instance.

## Runtime

```text
Python: 3.10.12
DB:     Cloud MySQL
ORM:    SQLAlchemy + PyMySQL
API:    FastAPI / Uvicorn
Worker: python -m worker.poller
Web:    Vite + Vue3
```

## Structure

```text
backend/
  app/                 FastAPI app, SQLAlchemy models, API routes
  worker/poller.py     long-running task polling worker
  scripts/             demo seed and smoke-check helpers
  storage/             uploaded originals and generated thumbnails
frontend/
  src/                 Vue3 dashboard, upload, image review UI
deploy/
  scale-api.service.example
  scale-worker.service.example
DB_SCHEMA.md           database structure and ERD
```

## Backend Setup

Create a Python 3.10.12 virtual environment:

```bash
cd /opt/scale/outputs/backend
python3.10 -m venv .venv
source .venv/bin/activate
python --version
pip install -r requirements.txt
cp .env.example .env
```

Edit `backend/.env` and set the company Cloud MySQL URL:

```env
DATABASE_URL=mysql+pymysql://scale_user:scale_password@cloud-mysql-host:3306/scale?charset=utf8mb4
```

Required environment values:

```env
APP_NAME=SCALE
API_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
STORAGE_DIR=/opt/scale/outputs/backend/storage
MEASUREMENT_RESULT_URL=http://measurement-server.local/tasks/{task_id}
MEASUREMENT_IMAGE_URL=http://measurement-server.local/tasks/{task_id}/image
WORKER_POLL_INTERVAL_SECONDS=3
WORKER_BATCH_SIZE=50
WORKER_CONCURRENCY=10
```

Run the API manually:

```bash
cd /opt/scale/outputs/backend
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The current starter creates tables on application startup with SQLAlchemy `Base.metadata.create_all()`. In production, replacing that with Alembic migrations is recommended.

## Worker

Run the polling worker manually:

```bash
cd /opt/scale/outputs/backend
source .venv/bin/activate
python -m worker.poller
```

The worker continuously reads due rows from `measurement_tasks`, calls the measurement server, parses ZIP/CSV results, creates `256x256` thumbnails, and writes `measurement_results`.

The web upload path creates `MOCK_...` tasks. The worker handles those tasks by generating deterministic mock calibration values so the same DB flow is exercised.

## Ubuntu Background Operation

On Ubuntu 22.04, run the API and worker as `systemd` services so they keep running after SSH disconnects and restart after failures.

The examples assume:

```text
Project path: /opt/scale/outputs
Linux user:   scale
Python venv:  /opt/scale/outputs/backend/.venv
```

If your server path or user is different, edit these files before installing:

```text
deploy/scale-api.service.example
deploy/scale-worker.service.example
```

Install services:

```bash
sudo cp deploy/scale-api.service.example /etc/systemd/system/scale-api.service
sudo cp deploy/scale-worker.service.example /etc/systemd/system/scale-worker.service
sudo systemctl daemon-reload
sudo systemctl enable scale-api.service
sudo systemctl enable scale-worker.service
sudo systemctl start scale-api.service
sudo systemctl start scale-worker.service
```

Check status:

```bash
sudo systemctl status scale-api.service
sudo systemctl status scale-worker.service
```

Follow logs:

```bash
journalctl -u scale-api.service -f
journalctl -u scale-worker.service -f
```

Restart after code changes:

```bash
sudo systemctl restart scale-api.service
sudo systemctl restart scale-worker.service
```

## Frontend

Local development:

```bash
cd frontend
npm.cmd install
npm.cmd run dev
```

Open:

```text
http://127.0.0.1:5173
```

Production build:

```bash
cd frontend
npm install
npm run build
```

The production output is created in:

```text
frontend/dist
```

Serve `frontend/dist` with the company web server or Nginx. If the frontend and API are served from different hosts, set `VITE_API_BASE_URL` at build time.

Example:

```bash
VITE_API_BASE_URL=http://scale-api.company.local:8000 npm run build
```

## Validation Demo

After the backend can connect to Cloud MySQL, seed deterministic demo data:

```bash
cd backend
source .venv/bin/activate
python -m scripts.seed_demo_data
```

The script prints each `measurement_results` row before inserting it into Cloud MySQL, so you can verify the exact demo values that will appear on the frontend chart.

Open the dashboard and set the check date to the date printed by the script.

To insert test data with different equipment names:

```bash
cd backend
source .venv/bin/activate
python -m scripts.seed_custom_equipment_data \
  --equipment TEST-EQP-101 TEST-EQP-202 \
  --date 2026-07-23 \
  --days 7 \
  --high-count 3 \
  --middle-count 3 \
  --prefix TESTRUN
```

This creates `equipments`, `measurement_tasks`, and `measurement_results` rows
for the requested equipment names. The script prints each `measurement_results`
row before insertion. Use a clear `--prefix` so test rows are easy to identify
by `external_task_id`.

Expected right-side table behavior:

```text
DEMO-SCALE-A01: H Mag. O, M Mag. O
DEMO-SCALE-B02: H Mag. O, M Mag. X
DEMO-SCALE-C03: H Mag. X, M Mag. X, status has issue text
DEMO-SCALE-D04: H Mag. X, M Mag. X, blank status
```

Run a read-only API smoke check while the API is running:

```bash
cd backend
source .venv/bin/activate
python -m scripts.smoke_check
```

The smoke check verifies that every registered equipment appears in the dashboard `equipment_status` rows.

## Key API Endpoints

```text
POST /api/tasks
GET  /api/dashboard
GET  /api/equipments
POST /api/issues
PUT  /api/issues/{issue_id}
POST /api/upload/mock
GET  /api/images
POST /api/calibration-overrides
```

## Recommended Next Production Steps

1. Add Alembic migrations.
2. Add authentication for admin upload, issue registration, and review override.
3. Replace mock upload integration with the real measurement server POST API.
4. Use object storage such as MinIO/S3 if image volume grows.
5. Add worker metrics and alerts for failed or stale tasks.
