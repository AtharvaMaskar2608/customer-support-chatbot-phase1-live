"""Phase-2 (Top-N Bot) conversational goldens — clusters F-M.

Scenario-based `ConversationalGolden`s grounded in the workbook's Phase-2 cases
(RAG + API integrated): intent routing (F), API transactional flows (G), API
error handling (H), data correctness (I), multi-intent & loop (J), ticket &
handoff (K), and keywords & session (L), plus regression (M). All 7 Phase-2
blocker cases (F7, G1, G5, H8, I1, I2, I3) are present and tagged.

The data-correctness blockers (I1-I3) and AuthToken cases (G5, H8) encode the
cross-client-leak and token-safety concerns: right client, right period, figures
matching the backend, and no internal-error leaks.
"""

from __future__ import annotations

from deepeval.dataset import ConversationalGolden

from evals.goldens._catalog import make_golden

PHASE2_GOLDENS: list[ConversationalGolden] = [
    # ---- F: Intent routing ----
    make_golden(
        case_id="F4",
        severity="medium",
        scenario="User starts by asking Jini to explain P&L (RAG), then mid-flow "
        "switches to 'actually just send it' (API report).",
        expected_outcome="Jini cleanly switches from the explanation path to the "
        "report-delivery flow, collecting any needed parameters, without losing the "
        "P&L context.",
        user_description="A client who thinks out loud and changes their mind partway "
        "through the conversation.",
    ),
    make_golden(
        case_id="F7",
        severity="blocker",
        scenario="User sends a garbled, low-confidence request Jini cannot route to "
        "any intent.",
        expected_outcome="Jini does not take a wrong action or guess an intent; it "
        "escalates to a human agent after failing to clarify.",
        user_description="A client whose messages are garbled and ambiguous, hard to "
        "map to any supported request.",
    ),
    # ---- G: API transactional ----
    make_golden(
        case_id="G1",
        severity="blocker",
        scenario="User requests a preset-range report ('P&L for this FY').",
        expected_outcome="Jini delivers the correct P&L document for the correct "
        "client and the exact requested period — right doc, right client, right "
        "period.",
        user_description="A straightforward client who wants their current-FY P&L "
        "with minimal back-and-forth.",
    ),
    make_golden(
        case_id="G5",
        severity="blocker",
        scenario="User makes any API-backed request; the flow must propagate the "
        "session AuthToken so only this client's data is fetched.",
        expected_outcome="The returned data belongs to the requesting client only, "
        "fetched via their own auth token — never another client's data.",
        user_description="A logged-in client making a routine report request during "
        "an authenticated session.",
    ),
    # ---- H: API error handling ----
    make_golden(
        case_id="H3",
        severity="high",
        scenario="A new client with no P&L history requests a P&L report (empty data "
        "from the backend).",
        expected_outcome="Jini shows a clean 'no data found for this period' message "
        "and does not crash, error out, or fabricate rows.",
        user_description="A newly onboarded client who has not traded yet and expects "
        "to see a report.",
    ),
    make_golden(
        case_id="H8",
        severity="blocker",
        scenario="An API call is made with an expired or invalid AuthToken.",
        expected_outcome="Jini handles the auth failure gracefully with a friendly "
        "message and no internal-error leak — no stack trace, HTTP code, or raw "
        "reason string reaches the user.",
        user_description="A client whose session token has silently expired mid-chat.",
    ),
    # ---- I: Data correctness (all blockers) ----
    make_golden(
        case_id="I1",
        severity="blocker",
        scenario="Client A requests a report; the system must return only Client A's "
        "data.",
        expected_outcome="Client A receives strictly their own data; no field, figure, "
        "or document from any other client ever appears (no cross-client leakage).",
        user_description="A privacy-conscious client who checks that the details shown "
        "are actually theirs.",
    ),
    make_golden(
        case_id="I2",
        severity="blocker",
        scenario="User asks for a specific period ('Last FY P&L').",
        expected_outcome="The delivered data matches exactly the requested financial "
        "year — not the current FY or an adjacent period.",
        user_description="A detail-oriented client who will notice if the period is "
        "off by a year.",
    ),
    make_golden(
        case_id="I3",
        severity="blocker",
        scenario="User cross-checks the ledger figures Jini surfaces against the "
        "backend source of truth.",
        expected_outcome="Every figure Jini reports matches the backend exactly; no "
        "number is rounded, recomputed, or altered by the bot.",
        user_description="A meticulous client who reconciles the bot's numbers against "
        "their own records line by line.",
    ),
    # ---- J: Multi-intent & loop ----
    make_golden(
        case_id="J1",
        severity="high",
        scenario="User packs two intents into one message ('Send my P&L and check my "
        "UCC status').",
        expected_outcome="Jini resolves both requests sequentially, then returns to "
        "the main menu — neither request is dropped.",
        user_description="An efficient client who batches several asks into a single "
        "message to save time.",
    ),
    # ---- K: Ticket & handoff ----
    make_golden(
        case_id="K1",
        severity="high",
        scenario="User asks to talk to a human ('talk to agent').",
        expected_outcome="Jini raises a Freshdesk ticket with a useful summary and "
        "metadata, and confirms the handoff with a ticket reference.",
        user_description="A client who has decided the bot cannot help and wants a "
        "human now.",
    ),
    make_golden(
        case_id="K5",
        severity="high",
        scenario="User asks to raise a ticket for an intent that already has an open "
        "ticket.",
        expected_outcome="Jini surfaces the existing ticket's status instead of "
        "creating a duplicate ticket.",
        user_description="A client following up on an issue they already reported "
        "earlier, unaware a ticket exists.",
    ),
    # ---- L: Keywords & session ----
    make_golden(
        case_id="L1",
        severity="medium",
        scenario="User types 'restart' in the middle of a report flow.",
        expected_outcome="Jini clears the in-flight flow state and returns to the main "
        "menu, keeping the session's language; no stale selections carry over.",
        user_description="A client who got confused mid-flow and wants to start over "
        "cleanly.",
    ),
    make_golden(
        case_id="L3",
        severity="high",
        scenario="User types the AGENT keyword while Jini is waiting for date entry in "
        "a flow.",
        expected_outcome="The keyword intercepts before the date input is processed; "
        "Jini honors the agent handoff rather than treating 'AGENT' as a date value.",
        user_description="A frustrated client who bails out to a human right in the "
        "middle of entering parameters.",
    ),
    # ---- M: Regression ----
    make_golden(
        case_id="M3",
        severity="high",
        scenario="An API call fails during a session that also uses RAG answers; the "
        "failure must not corrupt subsequent RAG responses.",
        expected_outcome="After the API error, Jini's KB answers remain correct and "
        "grounded; the API failure does not contaminate the RAG path.",
        user_description="A client who hits a transient report failure and then goes "
        "back to asking how-to questions.",
    ),
]
