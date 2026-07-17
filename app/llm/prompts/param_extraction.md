# Parameter extraction

Extract only what the customer explicitly stated. Everything else stays null.

- `fy` — a financial year the customer named, e.g. "FY 2025-26", "financial year
  2024-25", or a bare "2025-26". Emit it as you read it; the router normalizes it
  to the long `"YYYY-YYYY"` form. If the customer gave an **Assessment Year**
  ("AY 2025-26", "assessment year 2025-26"), still fill `fy` with the year they
  said and note it is an AY in your reasoning — the router converts AY→FY and
  sets `needs_confirmation`.
- `date_range` — a `from`/`to` range the customer stated (e.g. "from 1 Apr 2024
  to 31 Mar 2025", "last month"). Only when concrete dates are present. Use ISO
  `YYYY-MM-DD`.
- `segment` — one of `equity`, `fno`, `commodity` when the customer names it
  ("equity", "cash", "F&O", "futures and options", "commodity", "MCX"). Keep it
  customer-facing; never emit an API group code.
- `report_format` — `pdf` or `excel` when stated.
- `delivery` — `in_chat` (default, "download", "here", "in chat") or `email`
  ("email it", "send to my email").

Never guess a financial year, date range, or segment the customer did not state.
