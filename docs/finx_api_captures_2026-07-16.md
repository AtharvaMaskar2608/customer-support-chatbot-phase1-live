# FinX API live captures — 2026-07-16 (sanitized)

> Source captures behind the reconciled endpoints in
> `technical/03_finx_api_reference.md`. Captured from the FinX Android app by
> the project owner. **Sanitized**: SessionIds, JWT, ClientId, and the
> registered email are replaced with placeholders — the originals must never
> be committed. Structure, field names, casing, and value types are verbatim.

## 1. PNL Download (`RequestFor: 0`)

```bash
curl 'https://finx.choiceindia.com/api/middleware/GetGlobalPNLPDF' \
  -X POST \
  -H 'authorization: <SESSION_ID>' \
  -H 'content-type: application/json' \
  -H 'from: android_9.2.1.260709' \
  --data-raw '{"ClientId":"<CLIENT_ID>","FromDate":"2026-04-01","Group":"Cash","RequestFor":0,"SessionId":"<SESSION_ID>","ToDate":"2026-07-21","UserId":"<CLIENT_ID>","With_Exp":true}'
```

Response:
```json
{
  "Status": "Success",
  "Response": "https://client-report.choiceindia.com/PDFReports/PNLReport_<REPORT_ID>_<CLIENT_ID>.pdf",
  "Reason": ""
}
```

## 2. PNL Email (`RequestFor: 1`)

Same request as #1 with `"RequestFor":1`.

Response:
```json
{
  "Status": "Success",
  "Response": "PnL Report mail sent successfully to <REGISTERED_EMAIL_UPPERCASED>",
  "Reason": ""
}
```

⚠️ Note: the confirmation string contains the full registered email,
uppercased — mask before display.

## 3. CML (third backend, JWT auth)

```bash
curl -X POST 'https://finx.choiceindia.com/mis/reports/generate' \
  -H 'authType: jwt' \
  -H 'source: FINX_ANDROID' \
  -H 'authorization: <SSO_JWT>' \
  -H 'from: android_9.2.2.260710' \
  --data '{"reportType":"cml","searchBy":"client-id","searchValue":"<CLIENT_ID>"}'
```

JWT claims observed (issuer `https://sso.choiceindia.com`, `client_id: FINX`,
RS256): `auth_time`, `exp`, `idp: local`, `mobile_number` (opaque), `nbf`,
`sub` (UUID). This is the frontend `accessToken`, NOT the SessionId.

Response: **not captured**.

## 4. Tax Report — Excel variant

```bash
curl -X POST 'https://finx.choiceindia.com/api/middleware/GetTaxReportPDF' \
  -H 'Authorization: <SESSION_ID>' \
  -H 'from: android_9.2.2.260710' \
  --data '{"ClientId":"<CLIENT_ID>","FileFormat":2,"FinYear":"2024-2025","RequestFor":2,"SessionId":"<SESSION_ID>"}'
```

Response: not captured (presumed `.xlsx` URL string, same envelope as PDF).

## 5. Ledger PDF

```bash
curl -X POST 'https://finx.choiceindia.com/api/middleware/GetLedgerDetailsPDF' \
  -H 'Authorization: <SESSION_ID>' \
  -H 'from: android_9.2.2.260710' \
  --data '{"ClientId":"<CLIENT_ID>","FromDate":"2026-07-01","Group":"GROUP1","LoginId":"<CLIENT_ID>","Margin":0,"RequestFor":0,"SessionId":"<SESSION_ID>","ToDate":"2026-07-22"}'
```

Response: **not captured**.

Notes: `Group` is `"GROUP1"` (uppercase, unlike the data API's `"Group1"`);
`LoginId` = client code (not `"JIFFY"`); `Margin: 0` on the normal ledger —
hypothesis `Margin: 1` = MTF (unconfirmed).

## 6. Contract Note (matches documented endpoint)

```bash
curl -X POST 'https://finx.choiceindia.com/middleware-go/report/contract' \
  -H 'Authorization: <SESSION_ID>' \
  -H 'from: android_9.2.2.260710' \
  --data '{"client_id":"<CLIENT_ID>","from_date":"2024-07-15","to_date":"2026-07-15"}'
```

Response: not captured over a traded range (only the 204 no-data envelope is
known from the original documentation).

## Android app enums (authoritative where they apply)

```kotlin
enum class ViewType(val serverValue: Int) {
    Mail(1),
    Download(2)
}

enum class FileFormatType(val serverValue: Int) {
    Pdf(1),
    Excel(2)
}
```

⚠️ `RequestFor` observed values do NOT follow ViewType uniformly:
`GetTaxReportPDF` matches (2=download, 1=email); `GetGlobalPNLPDF` and
`GetLedgerDetailsPDF` use 0=download. `RequestFor=1`=email is the only
cross-endpoint constant. See `technical/03_finx_api_reference.md` §2.

## Captures still owed

- MTF Ledger via `GetLedgerDetailsPDF` (expect `Margin: 1`)
- `GetLedgerDetailsPDF` success/failure response
- CML `/mis/reports/generate` response (verify `cmlLink` + 120s expiry)
- Contract-note list over a traded range (success `Body` field names)
- Contract-note per-note download endpoint (`file_id` → URL)
- `GetGlobalPNLPDF` failure envelope
- Tax Excel response URL
