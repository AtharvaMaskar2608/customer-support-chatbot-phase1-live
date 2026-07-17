# Intent taxonomy (16 intents)

Classify into exactly one of these values. The eleven `report_*` intents are
report flows; the other five are non-report.

## Report intents (11)

- `report_pnl` — Profit & Loss statement ("P&L", "PnL", "profit and loss").
- `report_ledger` — Ledger / account statement of funds.
- `report_mtf_ledger` — MTF (Margin Trading Facility) ledger specifically. Keep
  this when the customer says "MTF" even though it also contains "ledger".
- `report_contract_notes` — Contract notes / trade confirmations.
- `report_tax` — Tax Report for a financial year.
- `report_capital_gain` — Capital Gain ("capital gain", "CG"). Fulfilled by the
  Tax Report flow; it carries a Capital-Gain education line.
- `report_tax_pnl` — Tax P&L. Fulfilled by the Tax Report flow; it carries a
  Tax-P&L education line.
- `report_cml` — Client Master List (CML).
- `report_brokerage` — Brokerage charges / slab card.
- `report_holding` — Holding statement. (Classifiable but BLOCKED downstream — no
  captured file-delivery endpoint. Still classify it; the orchestrator handles
  the not-yet-available message.)
- `report_global_detail` — Global detailed report. (Also BLOCKED downstream;
  still classify it.)

## Non-report intents (5)

- `rag_qa` — a process / how-to / conceptual question answered from the knowledge
  base (e.g. "how do I check my trade details?", "what are the charges for FnO?").
- `raise_ticket` — the customer wants to raise a support ticket.
- `ticket_status` — the customer asks about an existing ticket's status.
- `call_support` — the customer wants to talk to a human / call support.
- `smalltalk_fallback` — greetings, thanks, chit-chat, or anything that fits none
  of the above.

## §2.5 intent precedence (a deterministic layer enforces this after you)

- "tax" beats "p&l": a message naming both resolves to the Tax Report.
- "capital gain" / "CG" → `report_capital_gain` (routes to the Tax flow).
- "holding statement" → `report_holding`, NOT `report_ledger`.
- bare "P&L" / "PnL" → `report_pnl`.

Pick your best single intent; the precedence layer only corrects these known
report-vs-report cases and never overrides a `rag_qa`/non-report classification.
