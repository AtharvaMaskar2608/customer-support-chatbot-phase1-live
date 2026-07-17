# FinX (Choice India) — Middleware API

Base URL: `https://finx.choiceindia.com/api/middleware`

## Conventions

- All requests are `POST` with `Content-Type: application/json`.
- Authentication is passed via the `authorization` header carrying the SessionId; on `/api/middleware` endpoints the same SessionId is repeated in the JSON payload.
- Successful responses return HTTP `200 OK` with an `authstatus: Authorized` response header.
- Errors are in-band: HTTP status is `200` even for failures — check `Status` in the body.

Response envelope (`/api/middleware`):

```json
{
  "Status": "Success",
  "Response": [ ... ],
  "Reason": ""
}
```

Common request fields:

| Field | Type | Description | Example |
|---|---|---|---|
| `LoginId` | string | Platform/application identifier | `"JIFFY"` |
| `ClientId` | string | Client (trading account) code | `"X493657"` |
| `SessionId` | string | Active session token (same as `authorization` header) | `"<SESSION_ID>"` |

---

# 1. Ledger

---

## 1.1 Get Ledger Details

Fetches ledger entries — vouchers, debits, credits, settlements — for a client over a date range. The first record in a full-period query is typically the OPENING voucher carrying the opening balance, and date ranges align with the Indian financial year.

**Endpoint**

```
POST /api/middleware/GetLedgerDetails
```

**Headers**

```http
Content-Type: application/json
authorization: <SESSION_ID>
origin: https://finx.choiceindia.com
```

**Request payload**

```json
{
  "LoginId": "JIFFY",
  "ClientId": "X493657",
  "Group": "Group1",
  "FromDate": "2026-04-01",
  "ToDate": "2026-07-15",
  "SessionId": "<SESSION_ID>"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `LoginId` | string | Yes | Platform identifier ("JIFFY") |
| `ClientId` | string | Yes | Client code |
| `Group` | string | Yes | Ledger group selector (e.g. "Group1") |
| `FromDate` | string | Yes | Start date, YYYY-MM-DD |
| `ToDate` | string | Yes | End date, YYYY-MM-DD |
| `SessionId` | string | Yes | Active session token |

**Response**

```json
{
  "Status": "Success",
  "Response": [
    {
      "trd_Date": "1900-01-01T00:00:00",
      "vDate": "",
      "voucher": "OPENING",
      "Trans_Type": "O",
      "No": "",
      "Code": "",
      "Narration": "Opening Balance",
      "ChqNo": 0.0,
      "Debit": 0.00,
      "Credit": 0.00,
      "settlement_No": 0.0,
      "Mkt_Type": "",
      "FinStyr": 0.0,
      "dt": "1900-01-01T00:00:00"
    }
  ],
  "Reason": ""
}
```

**Response fields**

| Field | Type | Description |
|---|---|---|
| `trd_Date` | string | Trade date (ISO datetime). 1900-01-01T00:00:00 acts as a null sentinel on the opening row |
| `vDate` | string | Voucher date (may be empty) |
| `voucher` | string | Voucher type, e.g. "OPENING" |
| `Trans_Type` | string | Transaction type code, e.g. "O" = Opening |
| `No` | string | Voucher / reference number |
| `Code` | string | Account or scrip code for the entry |
| `Narration` | string | Human-readable description |
| `ChqNo` | number | Cheque number (0 when not applicable) |
| `Debit` | number | Debit amount |
| `Credit` | number | Credit amount |
| `settlement_No` | number | Exchange settlement number (0 when not applicable) |
| `Mkt_Type` | string | Market / segment type (NSE / BSE segment identifier) |
| `FinStyr` | number | Financial-year indicator |
| `dt` | string | Entry datetime (ISO format) |

---

## 1.2 Get MTF Ledger Details

Fetches Margin Trading Facility (MTF) ledger entries for a client over a date range. The envelope and record schema match Get Ledger Details — an array of entries whose first record on a full-period query is the OPENING voucher.

> ⚠️ Verification needed — the captured MTF request is identical to the standard Ledger request (same endpoint, payload, and Group: "Group1"). Typically the MTF variant differs (a different Group value, an extra flag, or a distinct endpoint). Re-capture with the MTF Ledger tab active and update this section if a differing field is found.

**Endpoint**

```
POST /api/middleware/GetLedgerDetails
```

**Headers**

```http
Content-Type: application/json
authorization: <SESSION_ID>
origin: https://finx.choiceindia.com
```

**Request payload**

```json
{
  "LoginId": "JIFFY",
  "ClientId": "X493657",
  "Group": "Group1",
  "FromDate": "2026-04-01",
  "ToDate": "2026-07-15",
  "SessionId": "<SESSION_ID>"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `LoginId` | string | Yes | Platform identifier ("JIFFY") |
| `ClientId` | string | Yes | Client code |
| `Group` | string | Yes | Ledger group selector ("Group1" as captured) |
| `FromDate` | string | Yes | Start date, YYYY-MM-DD |
| `ToDate` | string | Yes | End date, YYYY-MM-DD |
| `SessionId` | string | Yes | Active session token |

**Response**

```json
{
  "Status": "Success",
  "Response": [
    {
      "trd_Date": "1900-01-01T00:00:00",
      "voucher": "OPENING",
      "Trans_Type": "O",
      "Narration": "Opening Balance",
      "Debit": 0.00,
      "Credit": 0.00,
      "settlement_No": 0.0
    }
  ],
  "Reason": ""
}
```

---

# 2. PNL Report

---

## 2.1 Get Global PNL — Equity

Fetches the client's global P&L for the equity (cash) segment over a date range. Note this endpoint uses UserId (equal to the client code) instead of the LoginId field seen on Ledger endpoints.

**Endpoint**

```
POST /api/middleware/GetGlobalPNLNew
```

**Headers**

```http
Content-Type: application/json
authorization: <SESSION_ID>
origin: https://finx.choiceindia.com
```

**Request payload**

```json
{
  "UserId": "X493657",
  "ClientId": "X493657",
  "Group": "Cash",
  "FromDate": "2026-04-01",
  "ToDate": "2026-07-15",
  "With_Exp": 1,
  "SessionId": "<SESSION_ID>"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `UserId` | string | Yes | User code — same value as ClientId |
| `ClientId` | string | Yes | Client code |
| `Group` | string | Yes | Segment selector — "Cash" for equity |
| `FromDate` | string | Yes | Start date, YYYY-MM-DD |
| `ToDate` | string | Yes | End date, YYYY-MM-DD |
| `With_Exp` | number | Yes | Include expenses / charges in the computation (1 = yes; presumably 0 = no) |
| `SessionId` | string | Yes | Active session token |

**Response · no data (HTTP 200)**

```json
{
  "Status": "Fail",
  "Response": null,
  "Reason": "Data not found."
}
```

**Notes**

- Errors are in-band: always check Status in the JSON body — HTTP status is 200 even for "Data not found."
- Response is null (not an empty array) on failure.
- Success record schema pending — capture a request over a period with trades to document it.

---

## 2.2 Get Global PNL — Derivatives

Fetches the client's global P&L for the derivatives (F&O) segment. Identical to the Equity call with Group set to "Derv".

**Endpoint**

```
POST /api/middleware/GetGlobalPNLNew
```

**Headers**

```http
Content-Type: application/json
authorization: <SESSION_ID>
origin: https://finx.choiceindia.com
```

**Request payload**

```json
{
  "UserId": "X493657",
  "ClientId": "X493657",
  "Group": "Derv",
  "FromDate": "2026-04-01",
  "ToDate": "2026-07-15",
  "With_Exp": 1,
  "SessionId": "<SESSION_ID>"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `Group` | string | Yes | Segment selector — "Derv" for derivatives |
| `…` | — | — | All other fields identical to 2.1 Get Global PNL — Equity |

**Response · no data (HTTP 200)**

```json
{
  "Status": "Fail",
  "Response": null,
  "Reason": "Data not found."
}
```

**Notes**

- Same envelope and behavior as 2.1 — in-band errors, Response: null when no data.

---

## 2.3 Get Global PNL — Commodity

Fetches the client's global P&L for the commodity segment. Identical to the Equity call with Group set to "Comm".

**Endpoint**

```
POST /api/middleware/GetGlobalPNLNew
```

**Headers**

```http
Content-Type: application/json
authorization: <SESSION_ID>
origin: https://finx.choiceindia.com
```

**Request payload**

```json
{
  "UserId": "X493657",
  "ClientId": "X493657",
  "Group": "Comm",
  "FromDate": "2026-04-01",
  "ToDate": "2026-07-15",
  "With_Exp": 1,
  "SessionId": "<SESSION_ID>"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `Group` | string | Yes | Segment selector — "Comm" for commodity |
| `…` | — | — | All other fields identical to 2.1 Get Global PNL — Equity |

**Response · no data (HTTP 200)**

```json
{
  "Status": "Fail",
  "Response": null,
  "Reason": "Data not found."
}
```

**Notes**

- Same envelope and behavior as 2.1 — in-band errors, Response: null when no data.

---

# 3. Global Details Report

---

## 3.1 Get Detailed PNL

Fetches the detailed (transaction / scrip-level) P&L report for a client over a date range. Unlike GetGlobalPNLNew, UserId is a fixed platform value ("neuron"), there is no With_Exp field, and this endpoint also sends a client-version "from" header.

**Endpoint**

```
POST /api/middleware/GetDetailedPNL
```

**Headers**

```http
Content-Type: application/json
authorization: <SESSION_ID>
origin: https://finx.choiceindia.com
from: Web_finx.choiceindia.com_V_4.6.0.4
```

**Request payload**

```json
{
  "UserId": "neuron",
  "ClientId": "X493657",
  "Group": "Group1",
  "FromDate": "2026-04-01",
  "ToDate": "2026-07-15",
  "SessionId": "<SESSION_ID>"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `UserId` | string | Yes | Fixed platform value "neuron" — not the client code |
| `ClientId` | string | Yes | Client code |
| `Group` | string | Yes | Group selector ("Group1" — same value family as Ledger, not Cash/Derv/Comm) |
| `FromDate` | string | Yes | Start date, YYYY-MM-DD |
| `ToDate` | string | Yes | End date, YYYY-MM-DD |
| `SessionId` | string | Yes | Active session token |

**Response · no data (HTTP 200)**

```json
{
  "Status": "Fail",
  "Response": null,
  "Reason": "Data not found."
}
```

**Notes**

- Same in-band error behavior as other endpoints: HTTP 200 with Status: "Fail" and Response: null when no data exists.
- Success record schema pending — capture a request over a period with trades to document it.

---

## 3.2 Get Detailed PNL — Commodities

Fetches the detailed P&L report for the commodities segment. Identical to 3.1 with Group set to "Group23".

**Endpoint**

```
POST /api/middleware/GetDetailedPNL
```

**Headers**

```http
Content-Type: application/json
authorization: <SESSION_ID>
origin: https://finx.choiceindia.com
from: Web_finx.choiceindia.com_V_4.6.0.4
```

**Request payload**

```json
{
  "UserId": "neuron",
  "ClientId": "X493657",
  "Group": "Group23",
  "FromDate": "2026-04-01",
  "ToDate": "2026-07-15",
  "SessionId": "<SESSION_ID>"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `Group` | string | Yes | Group selector — "Group23" for commodities |
| `…` | — | — | All other fields identical to 3.1 Get Detailed PNL |

**Response · no data (HTTP 200)**

```json
{
  "Status": "Fail",
  "Response": null,
  "Reason": "Data not found."
}
```

**Notes**

- Same envelope and behavior as 3.1 — in-band errors, Response: null when no data.

---

# 4. Contract Notes

---

## 4.1 Get Contract Notes

Fetches contract notes for a client over a date range. This lives on the Go middleware: snake_case fields, header-only auth, and an HTTP-style semantic StatusCode in the body.

**Endpoint**

```
POST /middleware-go/report/contract
```

Full URL: `https://finx.choiceindia.com/middleware-go/report/contract`

**Headers**

```http
Content-Type: application/json
authorization: <SESSION_ID>
from: Web_finx.choiceindia.com_V_4.6.0.4
origin: https://finx.choiceindia.com
```

**Request payload**

```json
{
  "client_id": "X493657",
  "from_date": "2026-07-01",
  "to_date": "2026-07-08"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `client_id` | string | Yes | Client code |
| `from_date` | string | Yes | Start date, YYYY-MM-DD |
| `to_date` | string | Yes | End date, YYYY-MM-DD |

**Response · no data (HTTP 200)**

```json
{
  "StatusCode": 204,
  "Message": "No valid contract notes found for the given clientId and date range",
  "DevMessage": null,
  "Body": {}
}
```

**Response fields**

| Field | Type | Description |
|---|---|---|
| `StatusCode` | number | HTTP-style semantic code (204 = no content; expect 200 on success) |
| `Message` | string | Human-readable status message |
| `DevMessage` | string | null | Developer / debug message (null on normal responses) |
| `Body` | object | Response payload — empty object {} when no data |

**Notes**

- Only one report type exists for contract notes — no Group / segment variants.
- Check StatusCode in the body, not the HTTP status, to detect empty results.
- Success Body schema pending — capture a range with executed trades to document it (likely contract-note metadata / download links).

---

# 5. Tax Report

---

## 5.1 Get Tax Report PDF

Generates a tax report for a financial year and returns a direct download URL. Unlike other reports this takes a FinYear rather than a FromDate/ToDate range, and Response is a string (the file URL), not an array.

> ⚠️ The generated report URL appears to be unauthenticated once created — treat returned URLs as sensitive; anyone with the link may be able to fetch the report.

**Endpoint**

```
POST /api/middleware/GetTaxReportPDF
```

**Headers**

```http
Content-Type: application/json
authorization: <SESSION_ID>
from: Web_finx.choiceindia.com_V_4.6.0.4
origin: https://finx.choiceindia.com
```

**Request payload**

```json
{
  "ClientId": "X493657",
  "FinYear": "2025-2026",
  "RequestFor": 2,
  "FileFormat": 1,
  "SessionId": "<SESSION_ID>"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `ClientId` | string | Yes | Client code |
| `FinYear` | string | Yes | Financial year, YYYY-YYYY. Supported: "2024-2025", "2025-2026", "2026-2027" |
| `RequestFor` | number | Yes | Report variant selector (observed: 2; other values unverified) |
| `FileFormat` | number | Yes | Output format (1 = PDF; other values unverified) |
| `SessionId` | string | Yes | Active session token |

**Response · success**

```json
{
  "Status": "Success",
  "Response": "https://client-report.choiceindia.com/PDFReports/TaxReport_<REPORT_ID>_X493657.pdf",
  "Reason": ""
}
```

**Response fields**

| Field | Type | Description |
|---|---|---|
| `Status` | string | "Success" on success |
| `Response` | string | Download URL on client-report.choiceindia.com. Filename: TaxReport_<report id>_<ClientId>.pdf |
| `Reason` | string | Empty on success |

**Notes**

- Only three financial years are currently supported: 2024-2025, 2025-2026, 2026-2027.
- The file is generated server-side and hosted under https://client-report.choiceindia.com/PDFReports/ — clients download / open the returned URL.
