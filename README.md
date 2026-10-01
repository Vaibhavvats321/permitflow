# PermitFlow

Multi-tenant web app for city event permit applications. Organizers submit requests; agencies review them until the application is approved or rejected.

Local development uses two services: a FastAPI backend in `/api` and a Next.js frontend in `/web`.

Requires **Python 3.11+**, **Node.js 20+**, and **npm**. PostgreSQL is not required for this initial skeleton.

## Backend (`/api`)

```bash
cd api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Health check: [http://localhost:8000/health](http://localhost:8000/health)

## Frontend (`/web`)

```bash
cd web
npm install
npm run dev
```

App: [http://localhost:3000](http://localhost:3000)

## Configuration

Copy `.env.example` to `.env` and fill in local values. Do not commit `.env`. Environment variables are not loaded by the skeleton yet; they are listed so later phases have a single place for configuration.
