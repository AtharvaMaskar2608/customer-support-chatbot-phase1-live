## ADDED Requirements

### Requirement: Five conversational error codes

The system SHALL define an `ErrorCode` enum with exactly five codes — `E-NODATA`,
`E-YEAR`, `E-TIMEOUT`, `E-FETCH`, `E-UNKNOWN` — and an `ErrorCopy` config mapping
each code to its verbatim user-facing bubble copy and its recovery-chip set, as a
shared config reused by every flow. The copy SHALL be verbatim from the flow spec
§8.4:

- `E-NODATA` (API failure meaning no data in range): "No transactions found for FY
  {FY_short}, so there's nothing to report for that year." — chips: Try FY
  {defaultFY} (or another in-window year) · 🎫 Raise a ticket.
- `E-YEAR` (requested FY outside window, no API call): "I can pull Tax Reports for
  the current and last two financial years — that's {list}. Which one?" — chips:
  the 3 FY chips.
- `E-TIMEOUT` (API or byte-fetch timeout / network failure): "That took longer than
  it should — the report didn't come through. Your selections are saved." — chips:
  ↺ Retry · 🎫 Raise a ticket.
- `E-FETCH` (`Status: Success` but URL 404s / empty / wrong magic bytes): "The
  report generated but arrived incomplete on my side — let me redo it." then on
  retry failure "Still not coming through cleanly." — chips: ↺ Try again · ✉️
  Email me both · 🎫 Raise a ticket.
- `E-UNKNOWN` (any other `Status != "Success"`): "Something went wrong generating
  that report on our side." — chips: ↺ Retry · 🎫 Raise a ticket.

#### Scenario: Codes and copy are verbatim

- **WHEN** an error bubble is rendered
- **THEN** its copy SHALL match the flow spec §8.4 verbatim for its `ErrorCode`, with only the bracketed placeholders substituted

#### Scenario: Exactly five codes

- **WHEN** the `ErrorCode` enum is defined
- **THEN** it SHALL contain exactly `E-NODATA`, `E-YEAR`, `E-TIMEOUT`, `E-FETCH`, and `E-UNKNOWN`

### Requirement: Recovery chips per code

The system SHALL attach the code-specific recovery-chip set to each error, and the
🎫 raise-ticket and call-support paths SHALL remain reachable from error bubbles.
Error copy SHALL NOT expose `Reason` strings, HTTP status codes, or URLs; the raw
`Reason` SHALL be logged verbatim server-side only.

#### Scenario: No internal detail leaks to the user

- **WHEN** a FinX call fails and an error bubble is shown
- **THEN** the bubble copy SHALL NOT contain the `Reason`, HTTP code, or URL, and the `Reason` SHALL be logged server-side

### Requirement: E-FETCH silent auto-retry sequence

The system SHALL define `E-FETCH` as auto-retrying once silently before showing
the bubble's second line. The first line is shown only while the silent retry
runs; the second line ("Still not coming through cleanly.") is shown only if the
retry also fails.

#### Scenario: Second line only after retry fails

- **WHEN** byte validation fails and the silent retry also fails
- **THEN** the `E-FETCH` bubble SHALL show the second line with the ↺ Try again · ✉️ Email me both · 🎫 Raise a ticket chips

### Requirement: Partial dual-format email failure copy

The system SHALL define the EC-12 partial dual-format email-failure copy for all
email-capable flows: "Your PDF is on its way to {masked_email}, but the Excel
didn't go through." with chips ↺ Retry Excel · 📊 Get Excel here · 🎫 Raise a
ticket. The email SHALL be masked before display.

#### Scenario: Partial email failure tells the truth

- **WHEN** a dual-format email send delivers the PDF but not the Excel
- **THEN** the EC-12 copy SHALL be shown with the masked email and the three recovery chips
