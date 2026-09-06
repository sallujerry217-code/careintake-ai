# CareIntake AI

**Voice patient registration, from the first hello to a confirmed, persistent record.**

CareIntake combines a real Vapi phone agent, Groq GPT-OSS 120B, a validated FastAPI service, PostgreSQL, and a React patient workspace. Riley collects demographics naturally, accepts corrections, reads back every collected field, and saves only after explicit confirmation. Returning callers can verify and update their existing record.

> This project is a technical assessment/demo. It is not intended for real PHI or production HIPAA workloads. Use fictional patient information only.

## Demo

Deployment and telephone verification results are recorded in [docs/submission.md](docs/submission.md). Reviewer credentials are shared separately, never committed.

- Repository: https://github.com/salogamer2002/careintake-ai
- API / dashboard: deployment in progress; see submission notes for final status.
- U.S. number: provisioning in progress; see submission notes for final status.

## Architecture

```mermaid
flowchart LR
    Caller[Caller / U.S. number] <--> Vapi[Vapi: transcription + voice + interruption handling]
    Vapi <--> Groq[Groq: GPT-OSS 120B]
    Vapi -->|Authenticated tool calls| API[FastAPI]
    API --> Validation[Pydantic validation + patient service]
    Validation --> DB[(Persistent PostgreSQL)]
    Dashboard[React patient workspace] -->|Authenticated REST| API
    Vapi -->|End-of-call report| API
```

The speech pipeline streams inside Vapi; it does not wait for our backend to generate audio. FastAPI handles short validation, lookup, and persistence requests. This keeps telephony separate from patient storage and avoids rebuilding STT/TTS under a three-hour constraint.

## Features

- All required and optional demographic fields, UTC metadata, UUID identifiers.
- Full CRUD with partial `PUT`, exact last-name/DOB/phone filters, broad name/phone search and pagination.
- Phone normalization, real date validation, U.S. states/territories, ZIP/ZIP+4, name and insurance member ID validation.
- Database-enforced active-phone uniqueness and soft deletion; archived records remain in storage.
- Signed, call-bound preparation tokens, expiry, correction invalidation, explicit confirmation checks, and transactional retry receipts.
- Returning-caller verification before exposing an existing record.
- Authenticated dashboard: overview, patient directory, details, add/edit/archive, call history, and real service status.
- Truthful metrics, empty/error/loading states, responsive layouts, keyboard-accessible dialogs and destructive confirmation.
- Call outcome linking and optional transcript storage; dropped calls never imply successful registration.
- OpenAPI documentation at `/docs`, structured logs, request IDs, health checks, CI, Docker, and Railway configuration.

## Why this stack

**Vapi** provides phone provisioning, speech recognition, voice synthesis, turn-taking and interruption support. **Groq GPT-OSS 120B** provides fast instruction following and tool calling using the supplied provider key. **FastAPI/Pydantic** makes the HTTP schema and server validation compact and reviewable. **SQLAlchemy/PostgreSQL** provides typed persistence and atomic writes. **React/Vite/TypeScript** gives a small, fast dashboard build; CSS tokens provide a consistent visual system without a large framework. **One Railway app** serves both API and static dashboard, with a separate PostgreSQL service and persistent volume. Vercel remains an optional frontend deployment.

The supplied iHealth and InfoMary projects were reviewed for streaming patterns. Their medical advice/RAG pipelines are outside this registration task, so no clinical prompts or unrelated dependencies were copied. Vapi owns the streaming voice loop instead.

## Repository

```text
backend/app/          configuration, models, schemas, services, REST and Vapi adapter
backend/tests/        isolated validation, CRUD, confirmation and failure tests
frontend/src/         typed API client, dashboard and visual system
docs/                assistant JSON, system prompt, testing and submission notes
scripts/             assistant configuration and PostgreSQL smoke check
Dockerfile           production full-stack image
backend/Dockerfile   optional standalone API image
docker-compose.yml   local app + persistent PostgreSQL
railway.toml         deployment and health configuration
```

## Quick start — Docker

Prerequisite: Docker Engine/Compose running.

```bash
git clone https://github.com/salogamer2002/careintake-ai.git
cd careintake-ai
docker compose up --build
```

Open http://localhost:8000 for the dashboard and http://localhost:8000/docs for the API. Local Compose disables reviewer auth unless `ADMIN_API_KEY` is supplied. PostgreSQL persists in the `postgres_data` volume. `docker compose down` preserves it; do not use `down -v` unless you intend to erase local demo data.

## Quick start — separate processes

Python **3.12+** and Node **22+** recommended. Python 3.9 is unsupported.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
cd backend
uvicorn app.main:app --reload --port 8000
```

In a second terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` to port 8000. SQLite is a local-only fallback; it creates `backend/careintake.db` when started from `backend`. For local PostgreSQL set `DATABASE_URL=postgresql+psycopg://USER:PASSWORD@localhost:5432/DBNAME` in `backend/.env`. Use a dedicated database to avoid mixing unrelated projects. A localhost URL cannot connect from a cloud service to your laptop.

## Environment variables

Backend reads process environment and `.env` in its working directory.

| Variable | Purpose |
|---|---|
| `APP_ENV` | `development` or `production` |
| `DATABASE_URL` | PostgreSQL connection string; plain `postgres://` and `postgresql://` are normalized to psycopg |
| `ADMIN_API_KEY` | Bearer key for patient, call, and statistics routes; required in production |
| `VAPI_SECRET` | Shared `X-Vapi-Secret` webhook header; required to use voice tools |
| `SIGNING_SECRET` | Random 32+ character preparation signing secret; required in production |
| `CORS_ORIGINS` | Comma-separated exact frontend origins |
| `PHONE_NUMBER` | Configured U.S. number displayed in the dashboard |
| `VAPI_ASSISTANT_ID` | Assistant identifier used for configuration status |
| `STORE_TRANSCRIPTS` | Default false; enable only for fictional assessment calls |
| `AUDIT_PAYLOADS` | Default false; true logs final confirmed demographics for fictional assessment evidence |
| `LOG_LEVEL` | Default INFO |
| `STATIC_DIR` | Static dashboard directory; Docker sets this automatically |
| `PORT` | Docker listening port, default 8000 |
| `VITE_API_BASE_URL` | Optional separately hosted API base URL; never put secret keys in Vite |

Setup script only: `VAPI_API_KEY`, `GROQ_API_KEY`, `API_BASE_URL`, and optionally `VAPI_ASSISTANT_ID`. These do not need to be present on the API server. The Groq key is stored as a provider credential in Vapi.

## REST API

Success: `{"data": ..., "error": null}`. Failure: `{"data": null, "error": {"code": "...", "message": "...", "details": ...}}`. Lists return arrays in `data`, with pagination metadata alongside. All patient/call/statistics routes require `Authorization: Bearer <ADMIN_API_KEY>` when configured.

| Method | Route | Purpose |
|---|---|---|
| GET | `/health` | API and database readiness; 503 if unavailable |
| GET | `/config` | Public non-secret dashboard settings |
| GET | `/patients` | Active records; `last_name`, `date_of_birth`, `phone_number`, `q`, `limit`, `offset` |
| GET | `/patients/search/by-phone` | Normalized exact phone lookup |
| GET | `/patients/{uuid}` | One active record |
| POST | `/patients` | Create; returns 201 |
| PUT | `/patients/{uuid}` | Partial validated update; omitted fields are preserved |
| DELETE | `/patients/{uuid}` | Soft deletion; sets `deleted_at` |
| GET | `/calls`, `/calls/{uuid}` | Call history and details |
| GET | `/stats` | Active patients, registrations today, call counts and registration ratio |
| POST | `/webhooks/vapi` | Vapi custom tools and end-of-call events; separate webhook auth |

Input dates accept `MM/DD/YYYY` (assessment format) and ISO `YYYY-MM-DD`; storage and API responses use ISO to eliminate ambiguity. Dashboard renders dates in U.S. month-name format. Timestamps are UTC. Optional fields can be cleared with null. Required fields cannot. Unknown/read-only input fields are rejected. Phone matching assumes one active patient per phone in this demo.

### Examples

```bash
export API_BASE_URL=https://YOUR_DEPLOYMENT
# Set ADMIN_API_KEY in your shell from the separately provided reviewer notes.
curl "$API_BASE_URL/health"
curl -H "Authorization: Bearer $ADMIN_API_KEY" \
  -H 'Content-Type: application/json' -X POST "$API_BASE_URL/patients" \
  -d '{"first_name":"Morgan","last_name":"Bennet","date_of_birth":"02/08/1998","sex":"Female","phone_number":"732-555-0184","address_line_1":"27 Oak Street","city":"Somerset","state":"NJ","zip_code":"08873"}'
curl -H "Authorization: Bearer $ADMIN_API_KEY" "$API_BASE_URL/patients?last_name=Bennet"
curl -H "Authorization: Bearer $ADMIN_API_KEY" \
  -H 'Content-Type: application/json' -X PUT "$API_BASE_URL/patients/PATIENT_UUID" \
  -d '{"city":"Edison"}'
curl -H "Authorization: Bearer $ADMIN_API_KEY" -X DELETE "$API_BASE_URL/patients/PATIENT_UUID"
```

Staff REST operations are explicitly authenticated administrative actions; the voice confirmation gate applies to voice tools. The voice model has no admin API key and no direct database access.

## Voice setup

1. Deploy the app and PostgreSQL; confirm `GET /health` succeeds.
2. In Vapi, obtain a **private API key**. The assistant UUID is not a key.
3. Set setup environment variables, keeping secrets out of shell history where possible.
4. Generate and apply the configuration:

```bash
python scripts/build_vapi_config.py
python scripts/configure_vapi.py --assistant-id "$VAPI_ASSISTANT_ID" --provision-number
```

The script imports the Groq credential if absent, updates the assistant, configures tool/end-report HTTPS URLs and authentication, and provisions a Vapi U.S. number if none is attached. It never prints provider credentials. Vapi may require account verification, available credits, or an available area code. Number provisioning and call usage are governed by the provider; do not assume all usage is free.

Manual dashboard alternative: **Assistants → Riley → Model**: Groq / `openai/gpt-oss-120b`; paste [system prompt](docs/vapi-system-prompt.md). Voice: Vapi Elliot v2; transcriber: Deepgram nova-3 English. Add the function tools from [assistant JSON](docs/vapi-assistant.json). Set each tool server URL and the assistant server URL to `https://YOUR_API/webhooks/vapi`, with `X-Vapi-Secret` matching the backend. Subscribe to `tool-calls` and `end-of-call-report`. **Phone Numbers → Create Phone Number → Free Vapi Number**, choose an available U.S. area code, then assign Riley. Copy the number and assistant ID to the backend environment and redeploy.

### Confirmation design

`prepare_patient` returns validated data and a signed 15-minute token bound to the provider call. It does not create a Patient. Only a digest is stored in `voice_drafts`. Re-preparing replaces that digest; reset deletes it. `create_patient`/`update_patient` requires that latest token, a strict boolean `confirmed=true`, and an affirmative `confirmation_text` without obvious corrections/negation. Successful writes and tool receipts commit together. Retries return the same result; a token cannot be used by another call. Returning updates require a call-bound verification grant.

**Boundary:** caller approval text is supplied by the LLM. These checks prevent missing, stale, cross-call, and obviously negative confirmations; they are not independent proof of what was spoken. The prompt requires a new caller turn after complete read-back. Recorded call review is the final conversational acceptance test. A production system would add a provider-transcript state machine or DTMF consent independent of the model.

## Deployment

### Railway — recommended full stack

Create a project and add PostgreSQL with a persistent volume. Add this GitHub repository as an app service at the repository root. Railway uses the root Dockerfile and `/health`. Set `DATABASE_URL` to the internal PostgreSQL URL, `APP_ENV=production`, and random admin/webhook/signing secrets. Generate a public domain, set `CORS_ORIGINS` to that origin, and configure Vapi with that URL. The React build is served at `/`; API paths stay at the root. Do not mount an ephemeral SQLite database in production.

### Vercel — optional separate dashboard

Import the repository, choose `frontend` as Root Directory, Vite framework, build `npm run build`, output `dist`. Set `VITE_API_BASE_URL` to the Railway API origin. Add the resulting Vercel origin to backend `CORS_ORIGINS`. Enter the reviewer key at runtime; never put it in `VITE_*`. The included `frontend/vercel.json` handles SPA fallback. Vercel does not replace PostgreSQL or the persistent backend here.

## Verification

```bash
pytest backend/tests -q
cd frontend && npm ci && npm run build
# Dedicated test PostgreSQL only; fixture writes are rolled back:
TEST_DATABASE_URL=postgresql+psycopg://USER:PASS@HOST:5432/TEST_DB python scripts/postgres_smoke.py
```

Automated coverage includes required/optional field validation, normalized duplicate phones, partial updates, soft deletion retained in storage, lookup/filter errors, auth, database failure, call reports, preparation without save, positive/negative confirmation, corrections, reset, expiry, cross-call rejection, retries, and verified returning-caller updates. CI runs tests plus a PostgreSQL smoke test and frontend build. See [testing guide](docs/testing.md) for manual phone acceptance checks.

## Observability and trade-offs

Structured JSON logs include request IDs, method, path, status, timing, and patient operation IDs. Query strings, credentials and demographics are excluded by default. For the assessment's final-payload logging requirement, set `AUDIT_PAYLOADS=true` and use fictional data only; final confirmed voice payloads are then logged. `STORE_TRANSCRIPTS=true` stores provider transcripts linked to call outcomes. Even with transcript storage off, the provider may retain call artifacts and our call summaries may contain details; configure retention before any real-world use.

The initial schema is created at startup, suitable for this small demo. It is not a migration strategy for an evolving production database. One app instance is recommended for the assessment. PostgreSQL locks, uniqueness and transactional receipts protect main retry paths; a rare concurrent report may need provider retry. Voice verification by phone/name/DOB is a demo safeguard, not strong identity verification. A shared reviewer key is not role-based authentication. No medical or appointment functionality is included. U.S. number format validation is NANP syntactic validation, not carrier/geographic assignment verification.

## Next steps

Production identity/RBAC, independent consent verification, Alembic migrations, retention/cleanup jobs for drafts and receipts, automated conversational evaluations, multi-language speech testing, load testing, and operational backup/restore procedures.

## Provider references

- [Vapi Groq models](https://docs.vapi.ai/providers/model/groq)
- [Vapi custom tools](https://docs.vapi.ai/tools/custom-tools)
- [Vapi server authentication](https://docs.vapi.ai/server-url/server-authentication)
- [Vapi U.S. phone numbers](https://docs.vapi.ai/free-telephony)
- [Railway public API](https://docs.railway.com/integrations/api)
