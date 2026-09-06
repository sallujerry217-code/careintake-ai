# Submission review and latency findings

## Evidence (September 6, 2026)

The completed provider phone call at 05:35–05:46 UTC executed prepare_patient and create_patient; the create result reported saved=true. Vapi measured average turn latency 7,087.75 ms, model latency 4,515.5 ms, voice latency 225.6 ms and transcriber latency 113.35 ms. Several model turns exceeded 20 seconds. This is evidence of successful telephone-to-persistence integration, but the old response latency is not acceptable polish.

The supplied Groq key reports an 8,000 token/minute limit. The call consumed 147,633 prompt tokens over about ten minutes. Rate limits are a plausible contributor; this is not a trace-level proof of each pause. A short standalone GPT-OSS request completed in 0.75 seconds. The alternative Llama model was unavailable (404), and a Vapi managed-model chat check required billing setup (402). Neither failed alternative was deployed.

## Changes

- Shortened the system prompt and greeting; ask only the next missing field without repeated recaps.
- Kept ALL required fields, optional offer, corrections, verification, complete read-back and explicit approval.
- Reduced minimum response wait from 0.4 to 0.2 seconds; configured interruption handling.
- Reduced maximum generation to 1,200 tokens. Natural speech stays brief; final complete read-back is exempt from brief-response guidance.
- Synchronized appointment tool and prompt into the reproducible assistant generator.
- Fixed typed seed dates so fresh SQLite startup and tests work.
- Restricted voice appointments to a patient saved in the current call and explicit booking approval; validate appointment date through Pydantic.

## Assessment decision

Conditional SUBMIT: the deployed integration has completed a real registration, but call the updated assistant again before sending the submission. Do not claim the new latency is measured until that call is complete. Higher Groq quota remains the highest-value change for sustained low-latency conversations. A provider billing/key change is preferable to rebuilding telephony.

Keep Vapi + FastAPI + PostgreSQL. Twilio with custom speech would add implementation and operational risk. Retell is a valid alternative but migrating a working integration now requires new provisioning and conversational regression testing.

## Remaining P0/P1 checks

- Repeat a complete call, including correction, explicit approval and returning-patient lookup.
- Compare fresh provider turn latency with the old 7.1-second average.
- Ensure provider credits/quota cover the review window.
- Confirmation text is still an LLM assertion, not independently verified audio consent.
- Test fast speech, ambiguous dates, interruption, and hang-up with actual audio; HTTP tests cannot establish acoustic behavior.
- Appointment booking is fictional and must not be presented as a real clinic appointment.

A numerical hiring score would imply unverified conversational testing; no defensible 100/100 claim is made. Core validation/CRUD/confirmation paths have automated coverage; the fresh phone test determines final readiness.
