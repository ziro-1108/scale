# SCALE

SCALE is a FastAPI + MySQL + SQLAlchemy backend, a long-running polling worker, and a Vite + Vue3 frontend for equipment calibration monitoring.

## Structure

```text
backend/
  app/                 FastAPI app, SQLAlchemy models, API routes
  worker/poller.py     long-running task polling worker
  scripts/             demo seed and smoke-check helpers
  storage/             uploaded originals and generated thumbnails
frontend/
  src/                 Vue3 dashboard, upload, image review UI
  nginx.conf           production frontend reverse proxy config
docker-compose.yml     local Docker stack: MySQL, API, worker, frontend
```

Database structure:

```text
DB_SCHEMA.md
```

## Docker Quick Start

Run Docker commands from the project output directory:

```bash
cd outputs
```

Run the full local stack:

```bash
docker compose up --build
```

Run the full local stack in the background:

```bash
docker compose up -d --build
```

Open the frontend:

```text
http://127.0.0.1:8080
```

Direct API access is also exposed for debugging:

```text
http://127.0.0.1:8000/api/health
```

The Docker stack starts these services:

```text
mysql      MySQL 8.4 database, exposed on host port 3307
api        FastAPI backend, exposed on host port 8000
worker     polling worker that reads measurement_tasks continuously
frontend   Nginx static frontend, exposed on host port 8080
```

The API and worker share the same backend image and the same `scale_storage` volume, so uploaded images and generated thumbnails are visible to both services.

## Ubuntu Background Operation

For an Ubuntu 22.04 server, run SCALE in detached Docker mode:

```bash
cd /opt/scale/outputs
docker compose up -d --build
```

The `-d` option means detached mode. After this command finishes, the terminal can be closed and the containers keep running in the background.

The compose file already uses this restart policy for every service:

```yaml
restart: unless-stopped
```

This means Docker will restart `mysql`, `api`, `worker`, and `frontend` if a container exits unexpectedly or Docker restarts. The polling worker is included in Docker:

```yaml
worker:
  command: ["python", "-m", "worker.poller"]
```

Check background status:

```bash
docker compose ps
```

Follow worker logs:

```bash
docker compose logs -f worker
```

Restart only the worker:

```bash
docker compose restart worker
```

Stop everything intentionally:

```bash
docker compose down
```

## Ubuntu Boot Auto Start

To make SCALE start automatically after an Ubuntu reboot, register the compose stack with `systemd`.

First, place the project on the server. This README assumes:

```text
/opt/scale/outputs
```

If your actual path is different, update `WorkingDirectory` in `deploy/scale-compose.service.example`.

Install the service:

```bash
sudo cp deploy/scale-compose.service.example /etc/systemd/system/scale-compose.service
sudo systemctl daemon-reload
sudo systemctl enable scale-compose.service
sudo systemctl start scale-compose.service
```

Check service status:

```bash
sudo systemctl status scale-compose.service
docker compose ps
```

After this setup, Ubuntu can reboot and Docker will bring SCALE back in the background. For normal code updates, run:

```bash
cd /opt/scale/outputs
git pull
docker compose up -d --build
```

## Docker Service Commands

Run only the backend stack in the background:

```bash
docker compose up -d --build mysql api worker
```

This starts MySQL, the FastAPI backend, and the polling worker without starting the frontend container.

Run only the FastAPI backend in the background:

```bash
docker compose up -d --build mysql api
```

This is useful when you want to debug the API first and start the worker later.

Run only the worker in the background after MySQL and API are already running:

```bash
docker compose up -d --build worker
```

Run only the frontend container:

```bash
docker compose up -d --build frontend
```

Because `frontend` depends on `api`, this command can also start the API dependency if it is not already running.

Run the frontend container without starting dependencies:

```bash
docker compose up -d --no-deps --build frontend
```

Use this only when the backend is already running elsewhere. The frontend calls `/api` through Nginx, so API calls will fail if no backend is reachable from the Docker network.

Restart a single service after code or config changes:

```bash
docker compose up -d --build api
docker compose up -d --build worker
docker compose up -d --build frontend
```

Check running containers:

```bash
docker compose ps
```

## Docker Demo Validation

After the stack is running, seed deterministic demo data:

```bash
docker compose exec api python -m scripts.seed_demo_data
```

Then open the dashboard and set the check date to the date printed by the script.

Expected right-side table behavior:

```text
DEMO-SCALE-A01: H Mag. O, M Mag. O
DEMO-SCALE-B02: H Mag. O, M Mag. X
DEMO-SCALE-C03: H Mag. X, M Mag. X, status has issue text
DEMO-SCALE-D04: H Mag. X, M Mag. X, blank status
```

Run a read-only API smoke check:

```bash
docker compose exec api python -m scripts.smoke_check
```

The smoke check verifies that every registered equipment appears in the dashboard `equipment_status` rows.

## Docker Logs

Watch each service:

```bash
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f frontend
docker compose logs -f mysql
```

Stop the stack:

```bash
docker compose down
```

Stop the stack and remove local database/storage volumes:

```bash
docker compose down -v
```

## Using Company MySQL

The included `mysql` service is for local development. To use a company-provided MySQL server, update `DATABASE_URL` for both `api` and `worker` in `docker-compose.yml`.

```yaml
DATABASE_URL: mysql+pymysql://scale_user:scale_password@mysql-host:3306/scale?charset=utf8mb4
```

If you use an external MySQL server, you can remove or disable the `mysql` service and its `depends_on` references.

## Local Backend Setup

Docker is recommended, but the backend can still run directly:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

For production MySQL, set `DATABASE_URL` in `backend/.env`.

```env
DATABASE_URL=mysql+pymysql://scale_user:scale_password@mysql-host:3306/scale?charset=utf8mb4
```

The current starter creates tables on application startup. In production, replacing that with Alembic migrations is recommended.

## Local Worker

```bash
cd backend
python -m worker.poller
```

The worker continuously reads due rows from `measurement_tasks`, calls the measurement server, parses ZIP/CSV results, creates `256x256` thumbnails, and writes `measurement_results`.

The web upload path creates `MOCK_...` tasks. The worker handles those tasks by generating deterministic mock calibration values so the same DB flow is exercised.

## Local Frontend

```bash
cd frontend
npm.cmd install
npm.cmd run dev
```

Open:

```text
http://127.0.0.1:5173
```

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
