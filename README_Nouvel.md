# Nouvel — Electronic Medical System (EMS)

> **Status:** M1 shipped • M2 (Patient Intake) in progress  
> **Principle:** Access before features — Roles (RBAC) • Invite-only onboarding • Audit trail • `/whoami`

Nouvel is a pragmatic, privacy‑minded EMS. The foundation emphasizes secure access, clear roles, and auditable actions so clinical features can ship safely and fast.

---

## Contents
- [Architecture](#architecture)
- [What’s implemented](#whats-implemented)
- [Quick start](#quick-start)
- [Environment & settings](#environment--settings)
- [Project structure](#project-structure)
- [Auth & RBAC](#auth--rbac)
- [Audit logging](#audit-logging)
- [API docs & testing (Swagger)](#api-docs--testing-swagger)
- [Patient Intake (M2) — endpoints](#patient-intake-m2--endpoints)
- [Security notes](#security-notes)
- [Roadmap](#roadmap)
- [Portfolio summary (CAR)](#portfolio-summary-car)

---

## Architecture

**Backend**
- Django 5 + Django REST Framework (DRF)
- drf‑spectacular (OpenAPI/Swagger)
- Postgres‑ready (psycopg), SQLite by default for dev
- Redis + Celery ready in dependencies (not wired yet)
- WhiteNoise for static files (prod‑friendly)

**Apps (modular)**
- `apps.accounts` — custom user, invite acceptance flow, auth signals
- `apps.rbac` — roles and role bindings; DRF permission helper
- `apps.patients` — Patient model + search + duplicate check API
- `apps.appointments` — placeholder
- `apps.clinical` — placeholder
- `apps.documents` — placeholder
- `apps.audit` — audit model + helper

---

## What’s implemented

### ✅ M1 — Access before features
- **RBAC**: `Role` + `RoleBinding` models and admin UIs
- **Invite‑only onboarding**: admin creates invite → token link → set password → role auto‑bound
- **Auth audit trail**: `auth.login`, `auth.logout`, `auth.login_failed`, `invite.accepted` (with IP + user agent)
- **DX**: `/health`, `/api/docs` (Swagger), `/api/v1/auth/whoami` (identity + roles)

### 🚧 M2 — Patient Intake (Batch 1 complete)
- **Patient model**: demographics + contact + minimal address
- **Endpoints**:
  - `GET /api/v1/patients/?q=...` — quick search (name/email/phone/external_id)
  - `POST /api/v1/patients/` — create
  - `GET /api/v1/patients/{id}/` — view details
  - `POST /api/v1/patients/check-duplicates/` — early duplicate detection (email/phone or name+DOB)
- **Protection**: endpoints gated by roles (`clinician`, `staff`, `admin`) or superuser
- **Audit**: `patient.search`, `patient.create`, `patient.view`, `patient.duplicate_check`

---

## Quick start

### Requirements
- Python 3.13 (or a recent 3.12+)
- pip-tools (`pip-compile`, `pip-sync`)
- Optional: Postgres 14+, Redis 6+

### Setup
```bash
# clone repo then:
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -U pip setuptools wheel pip-tools
pip-compile requirements.in
pip-sync requirements.txt

# environment file (see vars below)
cp .env.example .env  # create and edit if present

# database
python manage.py migrate
python manage.py createsuperuser

# seed default roles
python manage.py seed_roles

# run
python manage.py runserver
```

Visit:
- Admin: http://127.0.0.1:8000/admin/
- API docs (Swagger): http://127.0.0.1:8000/api/docs/
- Health: http://127.0.0.1:8000/health

---

## Environment & settings

Key settings live in `config/settings/base.py` and environment overrides in `dev.py`/`prod.py` (if present). Suggested environment variables:

```
DJANGO_SECRET_KEY=change-me
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
DATABASE_URL=sqlite:///db.sqlite3
# e.g., DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/nouvel
CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000
```

Static files (prod): served via WhiteNoise; configure `STATIC_ROOT` during build.

---

## Project structure

```
nouvel/
  apps/
    accounts/    # custom User, invites, auth signals
    rbac/        # Role, RoleBinding, DRF permissions
    patients/    # Patient model, API, duplicate logic
    appointments/
    clinical/
    documents/
    audit/       # AuditEvent model + utils.log_event
  config/        # settings, urls, wsgi/asgi
  templates/     # Django templates
  static/        # assets
  requirements.in / requirements.txt
  manage.py
```

---

## Auth & RBAC

**Identity**
- Custom `User` (in `apps.accounts`).
- `/api/v1/auth/whoami/` returns: `id, username, email, display_name, is_staff, roles[]`.

**Roles**
- `Role(name, description)`
- `RoleBinding(user, role)` — unique per (user, role)

**DRF permission helper**
```python
# apps/rbac/permissions.py (usage)
from rest_framework.permissions import IsAuthenticated
from apps.rbac.permissions import roles_required

permission_classes = [IsAuthenticated, roles_required("clinician", "staff", "admin")]
```
Behavior:
- Case‑insensitive role matching
- Superusers always pass
- `admin` role passes all

**Invites**
- Admin creates an Invite (email + role + expiry).
- Recipient opens token URL, sets password; invite is single‑use and logged.

---

## Audit logging

**Model**: `AuditEvent` with `actor`, `action`, `object_type`, `object_id`, `ip`, `user_agent`, timestamps.  
**Helper**: `apps.audit.utils.log_event(request, action, object_type, object_id)`

**Captured (M1)**:
- `auth.login`, `auth.logout`, `auth.login_failed`, `invite.accepted`

**Captured (M2 Patients)**:
- `patient.search`, `patient.create`, `patient.view`, `patient.duplicate_check`

Browseable in Admin → **Audit events**.

---

## API docs & testing (Swagger)

OpenAPI docs at **`/api/docs/`** (drf‑spectacular).  
Testing flow (session auth):
1. Log into **`/admin/`** (grants `sessionid` + `csrftoken`).
2. Refresh **`/api/docs/`**.
3. Click **Try it out** on an endpoint → Execute.

Common responses:
- **401** — not logged in
- **403 CSRF** — missing CSRF for POST/PUT/DELETE (log into `/admin`, refresh docs)
- **403 Forbidden** — lacking required role
- **405** — wrong HTTP verb or missing trailing slash

Dev comfort (optional): enable `BasicAuthentication` alongside session auth in dev to use the padlock in Swagger without CSRF.

---

## Patient Intake (M2) — endpoints

```
GET  /api/v1/patients/?q=search     # quick search, role-gated
POST /api/v1/patients/              # create, role-gated
GET  /api/v1/patients/{id}/         # view details, role-gated
POST /api/v1/patients/check-duplicates/  # early duplicate detection
```

**Duplicate heuristic**
- Exact email or exact phone match → strong signal
- Exact (family + given + DOB) → strong signal
- Each candidate returns a simple score for UI hints

---

## Security notes

- Invite‑only onboarding; no public signup
- Role‑gated endpoints (least privilege)
- Audit of sensitive/auth actions
- Session auth + CSRF for admin/web; consider SSO in production
- HTTPS required in production

---

## Roadmap

- **M2 (Intake UX)**: form helpers, inline duplicate warnings, merge proposal draft
- **M3 (Scheduling)**: appointments, calendar views, reminders
- **M4 (Clinical)**: notes, orders, document upload, role‑aware access
- **M5 (Ops)**: reporting, exports, admin tooling

---

## Portfolio summary (CAR)

- **Challenge**: deliver an EMS foundation that is secure and audit‑ready from day one.  
- **Action**: ship RBAC, invite‑only onboarding, a full auth audit trail, and a small identity contract (`/whoami`); then implement Patient Intake with search, duplicate check, and audited access.  
- **Result**: a safe, testable base that accelerates clinical features and reduces operational risk.

---

**Docs**  
- Swagger: `/api/docs/`  
- Health: `/health`  
- Blog: `docs/m1-access-before-features.md`
