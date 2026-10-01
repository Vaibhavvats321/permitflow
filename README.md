# PermitFlow

Multi-tenant web app for city event permit applications. Organizers submit requests; agencies review them until the application is approved or rejected.

Local development uses two services: a FastAPI backend in `/api` and a Next.js frontend in `/web`.

Requires **Python 3.11+**, **Node.js 20+**, **npm**, and a running **PostgreSQL** database.

## Configuration

Environment variables are loaded at startup. The API reads the repo-root `.env`; the frontend reads `web/.env.local` (Next.js only loads env files from its own directory).

```bash
cp .env.example .env
```

In `.env`, set the database URLs and generate a JWT secret:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

`DATABASE_URL` is the connection the application uses and must belong to the restricted `permitflow_app` role. `DATABASE_URL_ADMIN` is the schema-owner connection used by migrations and seeding only.

Create `web/.env.local` with the API base URL:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Do not commit `.env` or `web/.env.local`. Only `NEXT_PUBLIC_*` variables are exposed to the browser, so never put a secret under that prefix.

## Backend (`/api`)

The virtual environment lives at the repo root, not inside `api/`.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r api/requirements.txt
python api/bootstrap_role.py
alembic -c api/alembic.ini upgrade head
python api/seed.py
uvicorn app.main:app --app-dir api --reload --port 8000
```

Run the steps in this order:

1. `bootstrap_role.py` creates and configures the restricted `permitflow_app` role from `APP_DB_PASSWORD`. It is idempotent, and does not modify any RLS policy.
2. `alembic upgrade head` creates the tables, enables Row-Level Security on all of them, and creates the `get_user_by_email` login helper. Migrations connect as the schema owner via `DATABASE_URL_ADMIN`, because the application role is intentionally not allowed to alter the schema.
3. `seed.py` adds the demo tenants, agencies, routing rules, and users. Also idempotent.

Health check: [http://localhost:8000/health](http://localhost:8000/health)

### Authentication

`POST /auth/login` takes an email and password and returns a JWT. `GET /auth/me` returns the authenticated user.

```bash
curl -X POST http://localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"springfield-organizer@example.com","password":"Demo1234!"}'

curl http://localhost:8000/auth/me -H "Authorization: Bearer $TOKEN"
```

Seeded accounts (`DEMO_USER_PASSWORD`, default `Demo1234!`):

| Email | Role | Agency |
| --- | --- | --- |
| `springfield-organizer@example.com` | Organizer | — |
| `springfield-reviewer@example.com` | Agency Reviewer | Police |
| `springfield-admin@example.com` | City Admin | — |
| `riverton-organizer@example.com` | Organizer | — |
| `riverton-reviewer@example.com` | Agency Reviewer | Fire |
| `riverton-admin@example.com` | City Admin | — |

Every row is scoped to its tenant by Row Level Security, so a Springfield token sees nothing belonging to Riverton.

The API allows browser requests from the origins in `CORS_ORIGINS` (default `http://localhost:3000`).

## Frontend (`/web`)

```bash
cd web
npm install
npm run dev
```

App: [http://localhost:3000](http://localhost:3000)
