# Submission — CareIntake AI

## Deliverables

| Item | Value |
|---|---|
| **Repository** | https://github.com/sallujerry217-code/careintake-ai |
| **API Base URL** | https://careintake-production.up.railway.app |
| **Dashboard URL** | https://careintake-production.up.railway.app/ |
| **U.S. Phone Number** | +1 (732) 707-9442 |
| **Voice Agent Name** | Riley (Vapi + Groq openai/gpt-oss-120b) |

The public repository is now owned by `sallujerry217-code`; Railway remains live and connected to the transferred repository.

Reviewer access key is shared separately. Use it as `Authorization: Bearer <key>` for protected REST endpoints or enter it in the dashboard. Use fictional patient information only.

## Reviewer Credentials

The `ADMIN_API_KEY` needed to access protected API endpoints and the dashboard will be provided separately (never committed to the repository).

Set the key as the `Authorization: Bearer <key>` header for API calls, or enter it in the dashboard login prompt.

## Verified Components

| Component | Status |
|---|---|
| Backend REST API (FastAPI) | ✅ Live — `/health` returns `connected` |
| PostgreSQL database (Railway) | ✅ Persistent — survives restarts |
| Voice agent (Vapi + Groq) | ✅ Active — assistant `360ba4ef` |
| U.S. phone number | ✅ Provisioned — +1 (732) 707-9442 |
| Dashboard (React + Vite) | ✅ Served from Railway at `/` |
| Automated tests | ✅ 20+ tests (API + voice webhook) |
| Seed data | ✅ 2 demo patients auto-inserted |
| Duplicate detection (bonus) | ✅ Returning callers recognized by phone |
| Appointment scheduling (bonus) | ✅ POST /appointments + voice tool |
| Call transcripts (bonus) | ✅ Stored via end-of-call reports |
| CI pipeline | ✅ GitHub Actions on push |

## Architecture

```
Caller → Vapi (STT/TTS + Groq LLM) → webhooks/vapi → FastAPI → PostgreSQL
                                                         ↕
                                              React Dashboard (/)
                                              REST API (/patients, /calls, /appointments, /stats)
```
