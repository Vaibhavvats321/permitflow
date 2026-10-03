# PermitFlow — Demo Setup

Portable, create-only demo data. One seeder command produces six demo tenants,
26 accounts, 12 agencies, 32 routing rules, 40 applications with full review
history — enough to exercise every screen in the City Admin module.

---

## 1. Prerequisites

| Requirement | Notes |
| --- | --- |
| Python 3.11+ | Verified on 3.13.7 |
| PostgreSQL 14+ | Local server, reachable on `localhost:5432` |
| Node.js 18+ | Only for the frontend |

No other services are required (no Redis, no message broker).

## 2. Install the backend

From the **repository root**:

```powershell
python -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install -r api\requirements.txt
```

> The virtualenv lives at the repository **root** (`.venv`), not inside `api\`.
> Every command below assumes that layout.

## 3. Configure

```powershell
Copy-Item .env.example .env
```

Then edit `.env` and replace the placeholders:

| Variable | What to put there |
| --- | --- |
| `DATABASE_URL` | Connection string for the restricted `permitflow_app` role (used by app code only). |
| `DATABASE_URL_ADMIN` | Connection string for a superuser/schema owner. Used **only** by migrations and seeding. |
| `APP_DB_PASSWORD` | Password `bootstrap_role.py` will set for `permitflow_app`. |
| `JWT_SECRET` | Generate one: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `DEMO_USER_PASSWORD` | Leave as `Demo1234!` — this is the password every demo account uses. |

Next.js reads its own env from `web/.env.local` (already set to
`http://localhost:8000`).

## 4. Create the schema

```powershell
& ".\.venv\Scripts\python.exe" api\bootstrap_role.py
& ".\.venv\Scripts\python.exe" -m alembic -c api\alembic.ini upgrade head
```

`bootstrap_role.py` creates/refreshes the `permitflow_app` role; `alembic`
applies all migrations (head: `e5b71d0c9a48`) as the schema owner.

## 5. Seed the demo data

One command, from the repository root:

```powershell
& ".\.venv\Scripts\python.exe" ".\api\seed_demo.py"
```

(equivalently `python api/seed_demo.py` if `python` already points at the venv)

**What it does**

* **Create-only** — never deletes, drops, truncates or alters anything; no
  schema, no RLS policies, no migrations. Database cleanup is a separate
  one-time manual step and is deliberately *not* part of the seeder.
* **Idempotent** — every row gets a deterministic `uuid5` id from a fixed
  namespace, so a repeat run reports `created=0 ... already present=N` and
  duplicates nothing.
* **Single transaction** — everything commits once; any failure rolls back, so
  a partial dataset can never be left behind.
* **Real business logic** — routing (including the automatic *Fire* agency
  above 5,000 expected attendance), status aggregation, transition guards,
  audit actions and password hashing all come from the application's own code.

Exit code `0` means the built-in verification passed (counts, passwords,
orphans, RLS). Non-zero means it rolled back — nothing was written.

**Expected output (verification section)**

```
tenants: 6        users: 26   (6 City Admin, 8 Organizer, 12 Agency Reviewer)
applications: 40  agencies=12  routing_rules=32
review_tasks=92   audit_events=156
password check: 26/26 accounts accept the demo password
orphaned child rows: 0
RLS enabled+forced: 7/7 tables, policies: 7/7
verification: PASSED
```

Applications per status: Approved 12, Rejected 8, Submitted 8,
Under Review 8, Changes Requested 4.

## 6. Start the app

Terminal 1 — API:

```powershell
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --app-dir api --reload --port 8000
```

Terminal 2 — Web:

```powershell
cd web
npm install
npm run dev
```

Open <http://localhost:3000>.

## 7. Sign in

Password for **every** demo account: `Demo1234!`
(`DEMO_USER_PASSWORD` in `.env`).

| Tenant | Accounts |
| --- | --- |
| City A | `admin.citya@permitflow.demo` (City Admin) · `organizer1.citya@permitflow.demo`, `organizer2.citya@permitflow.demo` (Organizer) · `police.citya@…`, `health.citya@…`, `fire.citya@…` (Agency Reviewer) |
| City B | same six addresses with `cityb` |
| City C | same six addresses with `cityc` |
| City D | same six addresses with `cityd` |
| City E | `admin.citye@permitflow.demo` (City Admin only — empty tenant) |
| City F | `admin.cityf@permitflow.demo` (City Admin only — empty tenant) |

Full list (26 addresses, domain `permitflow.demo`):

```
admin.citya@permitflow.demo        organizer1.citya@permitflow.demo    organizer2.citya@permitflow.demo
police.citya@permitflow.demo       health.citya@permitflow.demo        fire.citya@permitflow.demo
admin.cityb@permitflow.demo        organizer1.cityb@permitflow.demo    organizer2.cityb@permitflow.demo
police.cityb@permitflow.demo       health.cityb@permitflow.demo        fire.cityb@permitflow.demo
admin.cityc@permitflow.demo        organizer1.cityc@permitflow.demo    organizer2.cityc@permitflow.demo
police.cityc@permitflow.demo       health.cityc@permitflow.demo        fire.cityc@permitflow.demo
admin.cityd@permitflow.demo        organizer1.cityd@permitflow.demo    organizer2.cityd@permitflow.demo
police.cityd@permitflow.demo       health.cityd@permitflow.demo        fire.cityd@permitflow.demo
admin.citye@permitflow.demo        admin.cityf@permitflow.demo
```

**Verify login** — POST to the API:

```powershell
& ".\.venv\Scripts\python.exe" -c "import urllib.request,json;r=urllib.request.urlopen(urllib.request.Request('http://localhost:8000/auth/login',data=json.dumps({'email':'admin.citya@permitflow.demo','password':'Demo1234!'}).encode(),headers={'Content-Type':'application/json'}));print(json.loads(r.read())['role'])"
```

Expected: `City Admin`. Or sign in through the UI at
<http://localhost:3000> with any address above.

## 8. Reset / re-seed

* **Re-run the seeder** — safe at any time; it creates nothing twice.
* **Start over** — drop and recreate the database (or delete the demo rows by
  hand in FK order: `audit_events → review_tasks → applications →
  event_type_agency_rules → users → agencies → tenants`), then repeat
  steps 4–5. The seeder itself never cleans up, by design.

## 9. Notes & limitations

* Seeding runs on `DATABASE_URL_ADMIN` because Row Level Security is forced on
  all seven application tables — the restricted `permitflow_app` role cannot
  create tenants, by design. Never use that privileged string from app code.
* `City E` and `City F` are intentionally empty (admin only) so the
  empty-state UI can be demonstrated.
* The base routing matrix seeds **Police + Health** only; **Fire** is added
  automatically for applications above 5,000 expected attendance. Seeding Fire
  into the matrix would hide that override, so it is deliberately absent.
* Re-running with a *different* `DEMO_USER_PASSWORD` will not rewrite existing
  password hashes (create-only): reset them manually if you change it.
