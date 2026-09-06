# End-to-end acceptance test

Use fictional information only. Open the deployed dashboard with the separately supplied reviewer key.

1. Call the U.S. number from the submission notes. Riley should identify itself as the demo AI intake assistant.
2. Say: “My name is Morgan Bennett. I was born February eighth, nineteen ninety-eight.” It should capture both details without asking again.
3. Give an invalid phone: “123.” It should ask for a full phone number, not restart the entire interview. Correct to “732-555-0184.”
4. Provide sex Female, address 27 Oak Street, city Somerset, state New Jersey, ZIP 08873. These details can be provided in any order.
5. When offered optional fields, say “No insurance or emergency contact, thanks.”
6. During read-back say: “Actually, my last name is Bennet, with one T.” Riley should prepare the corrected record and read it back again.
7. Before approving, refresh Patients. There must be no new record.
8. Say: “Yes, all of that is correct.” Wait for Riley to confirm the save.
9. Search the dashboard for Bennet or query `/patients?phone_number=7325550184`. Check the corrected spelling, DOB, ZIP leading zero, generated UUID, and timestamps.
10. Call again with the same phone. Supply the matching name and DOB. Riley should recognize the returning record, ask whether to update, and avoid creating a duplicate.
11. Change city to Edison. Decline the first confirmation with a correction; approve only the final corrected read-back. Verify the original UUID remains.
12. Restart/redeploy the application and repeat the API query. The PostgreSQL record should remain.
13. Open the record, edit an optional field, save, then archive with the confirmation dialog. The active list and individual GET should exclude it; its database row remains with `deleted_at` set.

## Resilience checks

- Future DOB: “January first, 2099.” Expect a specific correction request.
- ZIP “123”: expect a request for a valid ZIP.
- “Start over”: the previous preparation must not be saveable.
- Hang up before final confirmation: no patient should be created.
- For a simulated backend failure, use the automated failure test; do not intentionally disable the live database during review.
- Replay the same webhook: no additional patient write or duplicate call event.

Automated tests do not prove telephone audio quality. The submission notes distinguish API/webhook tests, provider configuration checks, and actual human phone-call verification.
