# GCN-45 known defects (documented separately from the JMeter regression suite)

These are open product findings. They are NOT part of the eight scored JMeter scenarios, and no scenario threshold or assertion was relaxed to hide them.

| ID | Severity | Finding | Where reproduced | Why the JMeter suite is not affected |
|---|---|---|---|---|
| GCN45-D1 | Medium | A doctor-service outage makes `POST /api/appointments/{id}/payment/method` return a generic 500 instead of a retryable 503 (`DoctorPaymentClient` calls `EnsureSuccessStatusCode()`; the controller maps unknown exceptions to 500). | xUnit `qa-reports/GCN-45/xunit/known-defects/` (run-known-defect-repro.sh), expected 503, actual 500 | JM-08 asserts what must hold regardless of the fix: a 5xx class answer within 5 s with a message and no internal detail, nothing saved, reads still work, recovery works, bearer token forwarded. It does NOT assert 500 and does NOT assert 503. |
| GCN45-D2 | Low | Role "Pharmacy Staff" (with a space) is rejected with 403 by appointment-integration (`RequireRole("PharmacyStaff")` only), while doctor-payment-service accepts both spellings. user-auth normalizes issued tokens to `PharmacyStaff`, so only legacy or hand-made tokens are affected. | xUnit known-defect repro, expected 200, actual 403 | JM-03 uses the supported `PharmacyStaff` role only. |
| GCN45-O1 | Low (wording) | The shared online-payment helper shows "Only patients can pay for medicine orders." for every HTTP 403, including on appointment payments. | Vitest V1 pins the current text | Front-end only, not an API behaviour. |

## KD-D1 (optional sample, NOT included)
A strict "doctor outage must answer 503" JMeter sample was offered. It is deliberately not part of the passing suite and not in the JMX: it would fail today by design. If you want it, it can be added as a separate plan `GCN45-KD-D1.jmx` (one sample: stub down, select method, expect 503) that is run on its own and reported as an expected failure.

## GCN45-O2 (Low) Oversize PayHere notification answered 400, not 413  (found by JM-04 g, 2026-10-11)
`POST /api/appointment-payments/payhere/notify` carries `[RequestSizeLimit(64 * 1024)]`. A 70,000-byte (and a 1 MB) form body IS rejected before any payment code runs (nothing is stored, database evidence unchanged), but the response is `400 application/problem+json` "One or more validation errors occurred ... Failed to read the request form. Request body too large", not `413 Payload Too Large`.
Evidence: `evidence/JM-04g-oversize-webhook-probe.txt`, `results/readonly/results.jtl` (sample "JM-04 g body over 64 KB -> 413": expected 413, got 400).
Impact: the size limit works and is safe; only the status code differs from the HTTP convention and from the plan's expectation. The assertion in the plan has NOT been changed; JM-04 is reported FAIL until you decide how to treat it.

### GCN45-O2 root cause and classification (investigation 2026-10-11, `evidence/JM-04g-investigation.txt`)
- **The JMeter request is correct**: valid `application/x-www-form-urlencoded`, 70,009 bytes (> 65,536), URL and method right. An independent `curl` produces the identical answer, and so does the multipart variant (`known-defects/repro-GCN45-O2-oversize-webhook.sh`).
- **The limit works**: the body is rejected, the controller action never runs (its "PayHere callback rejected" warning is not logged for the oversize requests), no database row is touched.
- **Why 400**: the message "Failed to read the request form. {0}" is a resource string of `Microsoft.AspNetCore.Mvc.Core.dll` (ASP.NET 8.0.30). MVC's form value provider catches Kestrel's "Request body too large" while binding the form, records a model-state error, and `[ApiController]`'s automatic validation response turns it into `400 ValidationProblem` before the action is invoked.
- **Contract**: the code, the tests and the documents contain no requirement for 413 (search of src, tests, README: no match); the only declaration is `[RequestSizeLimit(64 * 1024)]`. The plan's expectation of 413 was an assumption about Kestrel, not a documented contract.
- **Classification**: genuine API-semantics deviation from HTTP convention (413 Payload Too Large), Low severity, not a security issue. It is NOT a faulty JMeter request. The assertion is unchanged, so JM-04 stays FAIL (9/10) until a decision is taken.
- **Possible fix (not applied, no production change without approval)**: map the form-read failure to 413, e.g. an exception filter / `ApiBehaviorOptions.InvalidModelStateResponseFactory` check for the "Request body too large" model error, or read the form inside the action and catch `BadHttpRequestException`.
