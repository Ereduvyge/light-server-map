# Light Server Map

A small FastAPI + HTMX + Jinja2 + async SQLAlchemy monitor.

Drag the handles to move cards on desktop.
Node statuses and the open software dialog refresh every 10 seconds.

![Map Screenshot](./.github/preview_imgs/map.png)

Click or tap a node to open its software dialog. Close with Escape, the close button, or the backdrop.

![Sevrer Screenshot](./.github/preview_imgs/server.png)

## Quickstart

### Run light-server-map with docker (persistent data)

Using the published GHCR image (easiest):

```sh
docker volume create light-server-map-data
docker run -d --name light-server-map --restart unless-stopped -p 3001:3001 --mount source=light-server-map-data,target=/app/data ghcr.io/ereduvyge/light-server-map:latest
```

Or fork repository, add actions secrets (GITHUB_TOKEN at minimum) and run build.

When updating, pull the image and recreate the container with the **same named
volume**. Do not remove that volume. The workflow publishes both a commit SHA tag
and `latest`, and its optional deployment example includes the data mount.


### Build and run with compose

```sh
docker compose up -d --build
```

The Compose file mounts the named volume `app-data` at `/app/data` and uses
`sqlite+aiosqlite:////app/data/monitor.db`. Rebuilding or recreating the container
keeps this database.

After code/image updates:

```sh
docker compose up -d --build
```

`docker compose down` keeps the volume. **`docker compose down -v` deletes it.**
For a simple backup, stop the app and copy the database/volume before restarting.
A bind mount can also be used; its directory must be writable by container UID
10001. The image runs as this non-root user.


`GET /healthz` is a lightweight app liveness endpoint, also used by Docker's
health check. Logs are available through `docker compose logs -f app`.


## Run locally

Use Python 3.13 or newer (the Docker image uses Python 3.13).

```sh
pip install -r requirements.txt
python -m uvicorn app:app --host 0.0.0.0 --port 3001 --reload
```

Open **http://localhost:3001/**. 

Linux hosts need the `ping` executable (Debian/Ubuntu: `iputils-ping`; macOS and
Windows include it). The Docker image installs it. ICMP must be permitted by the
host/container network; a machine blocking ICMP will appear unreachable.

HTMX 2.0.8 loads from a pinned jsDelivr URL, so the browser needs CDN access for
interactive behavior. CSS, icons, and application JavaScript are served locally.
There is no frontend build step.

## Configuration and database

Copy `.env.example` to `.env` if you want to override the defaults. Environment
variables take precedence.

| Variable | Default | Meaning |
| --- | --- | --- |
| `APP_ENV` | `development` | `test` selects in-memory SQLite unless a URL is explicitly provided |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/monitor.db` | Async SQLAlchemy connection URL |
| `MONITORING_ENABLED` | `true` | Start scheduled monitoring |
| `SCHEDULE_SYNC_SECONDS` | `10` | How often to reconcile jobs with database preferences |
| `CHECK_TIMEOUT_SECONDS` | `5` | Timeout for each network check |
| `CHECK_CONCURRENCY` | `20` | Maximum simultaneous checks |
| `LOG_LEVEL` | `INFO` | Loguru level; logs go to stderr |
| `ADMIN_PASSWORD` | `admin` | Password for the SQLAdmin interface at `/admin` |

SQLite is the default for local use and Docker. Its directory and missing tables
are created at startup. For tests, use:

APP_ENV=test

The constant in `db/models.py` is `sqlite+aiosqlite:///:memory:`.
A PostgreSQL URL such as `postgresql+asyncpg://user:password@host/monitor` is also
supported. `create_all()` creates missing tables; **it does not migrate existing
schemas**. Use migrations before changing an existing deployment's schema.

## Add your own nodes and software

Open **http://localhost:3001/admin** and enter `ADMIN_PASSWORD` (default: `admin`).
No username is needed. SQLAdmin provides node and software creation, editing,
details, and deletion. Check results are displayed but cannot be edited in the
forms. Choose a node in the software form to link the software to it.

Set `ADMIN_PASSWORD` in `.env` or the process environment to change the password.


You can also add records with the Python CRUD helper:

```python
import asyncio

from db.db_manager import db_manager
from db.models import Node, Software, engine, init_db


async def main():
    try:
        await init_db()
        node = await db_manager.create_entity(
            Node,
            name="Application server",
            ip="192.168.1.10",
            ping_check_enabled=True,
            ping_check_every=30,
        )
        await db_manager.create_entity(
            Software,
            node_id=node.id,
            name="API",
            domain="http://192.168.1.10",
            port=8080,
            health_check_path="/health",
            health_check_enabled=True,
            health_check_every=60,
        )
    finally:
        await engine.dispose()


asyncio.run(main())
```

All intervals are **positive integers in seconds**. Checks are disabled by default.
Use `ping_check_enabled` / `ping_check_every` on `Node` and
`health_check_enabled` / `health_check_every` on `Software`.
A software HTTP check runs independently of its node's ping check.

`domain` accepts a hostname or an HTTP(S) base URL. Without a scheme, port 443
selects HTTPS; other ports select HTTP. An explicit port in the URL overrides
`port`; otherwise the model's port is used (default 443).
The health path is appended to the base path. Credentials, query strings, and
fragments in the base URL are not accepted.

A direct **200–299** response is healthy. Redirects are not followed, and other
codes, connection errors, TLS failures, and timeouts are unhealthy. Only response
headers are needed, so large or streaming bodies are not downloaded.
Database-type software currently uses the same HTTP check.

Status is green for success, red for failure, amber before the first check, and
gray when disabled. The latest result and check timestamp are stored in the
database; timestamps are displayed in UTC.


APScheduler loads enabled records at startup, checks them immediately, then uses
their individual intervals. The reconciliation job adds, reschedules, and removes
jobs as records change. Each scheduled check reloads its record and skips it if
it has been disabled or deleted. Reload/refresh the map after adding or deleting
nodes; status updates are automatic.