"""T8: delivery assembly (proposal §Byte-validation…, §Delivery, §Per-flow cache)."""

from __future__ import annotations

from datetime import date

from app.contracts.errors import ErrorCode
from app.contracts.flow import selection_cache_key
from app.contracts.router import DateRange, Delivery, ExtractedParams, Intent, ReportFormat
from app.contracts.wire import Bubble, ChipRow, ErrorBubble, FileCard

from app.engine.cache import SelectionCache
from app.engine.delivery import deliver, mask_email
from app.engine.faults import FinXFetchError, FinXTimeoutError
from app.engine.ports import EmailResult, NoData, ReportBytes, ReportUrl
from tests.engine.conftest import FakeByteFetcher, FakeFlow, make_ctx

PDF = b"%PDF-1.7" + b"\x00" * (200 * 1024 - 8)  # ~200 KB
PARAMS = ExtractedParams(
    segment=None,
    date_range=DateRange(from_=date(2024, 4, 1), to=date(2024, 6, 30)),
    delivery=Delivery.in_chat,
)


def _pnl(**over):
    return FakeFlow(intent=Intent.report_pnl, title="P&L Statement", **over)


async def test_url_delivery_builds_renamed_file_card():
    flow = _pnl(generate_results=[ReportUrl("https://client-report/PDFReports/x.pdf")])
    fetcher = FakeByteFetcher([PDF])
    blocks = await deliver(flow, PARAMS, make_ctx(fetcher=fetcher))
    assert len(blocks) == 1 and isinstance(blocks[0], FileCard)
    card = blocks[0]
    assert card.filename == "P&L Statement.pdf"  # renamed, no Client ID
    assert "X008593" not in card.filename
    assert card.size_label == "200 KB"
    assert card.format == "pdf"
    assert fetcher.calls == 1 and flow.generate_calls == 1


async def test_fetch_error_triggers_exactly_one_silent_retry_then_succeeds():
    flow = _pnl(generate_results=[ReportUrl("u1"), ReportUrl("u2")])
    fetcher = FakeByteFetcher([FinXFetchError("bad magic"), PDF])
    blocks = await deliver(flow, PARAMS, make_ctx(fetcher=fetcher))
    assert isinstance(blocks[0], FileCard)
    assert fetcher.calls == 2 and flow.generate_calls == 2  # one silent retry


async def test_second_fetch_error_surfaces_e_fetch():
    flow = _pnl(generate_results=[ReportUrl("u1"), ReportUrl("u2")])
    fetcher = FakeByteFetcher([FinXFetchError("x"), FinXFetchError("y")])
    blocks = await deliver(flow, PARAMS, make_ctx(fetcher=fetcher))
    assert isinstance(blocks[0], ErrorBubble) and blocks[0].code is ErrorCode.E_FETCH
    assert fetcher.calls == 2 and flow.generate_calls == 2  # exactly one retry, no more


async def test_timeout_maps_to_e_timeout_without_retry():
    flow = _pnl(generate_results=[ReportUrl("u1")])
    fetcher = FakeByteFetcher([FinXTimeoutError("slow")])
    blocks = await deliver(flow, PARAMS, make_ctx(fetcher=fetcher))
    assert isinstance(blocks[0], ErrorBubble) and blocks[0].code is ErrorCode.E_TIMEOUT
    assert fetcher.calls == 1 and flow.generate_calls == 1  # no retry on timeout


async def test_no_data_maps_to_e_nodata():
    flow = _pnl(generate_results=[NoData(reason="Data not found.")])
    blocks = await deliver(flow, PARAMS, make_ctx(fetcher=FakeByteFetcher([])))
    assert isinstance(blocks[0], ErrorBubble) and blocks[0].code is ErrorCode.E_NODATA


async def test_cache_hit_skips_generate_and_fetch():
    flow = _pnl(generate_results=[ReportUrl("u1")])
    cache = SelectionCache()
    ctx = make_ctx(cache=cache, fetcher=FakeByteFetcher([PDF]))
    cache.put(selection_cache_key(flow.intent, PARAMS), PDF, now=ctx.now)
    blocks = await deliver(flow, PARAMS, ctx)
    assert isinstance(blocks[0], FileCard)
    assert flow.generate_calls == 0 and ctx.byte_fetcher.calls == 0


async def test_resend_bypasses_cache():
    flow = _pnl(generate_results=[ReportUrl("u-fresh")])
    cache = SelectionCache()
    ctx = make_ctx(cache=cache, fetcher=FakeByteFetcher([PDF]))
    cache.put(selection_cache_key(flow.intent, PARAMS), b"%PDF-stale", now=ctx.now)
    blocks = await deliver(flow, PARAMS, ctx, resend=True)
    assert isinstance(blocks[0], FileCard)
    assert flow.generate_calls == 1 and ctx.byte_fetcher.calls == 1  # regenerated fresh


async def test_cml_keeps_server_filename():
    flow = FakeFlow(intent=Intent.report_cml, title="CML", generate_results=[ReportUrl("u")])
    blocks = await deliver(flow, ExtractedParams(), make_ctx(fetcher=FakeByteFetcher([PDF])))
    assert isinstance(blocks[0], FileCard)
    assert blocks[0].filename == "Client_Master_List.pdf"  # exception: not renamed


async def test_report_bytes_path_no_fetch_and_caches():
    flow = FakeFlow(intent=Intent.report_contract_notes, title="Contract Note", generate_results=[ReportBytes(PDF)])
    cache = SelectionCache()
    ctx = make_ctx(cache=cache, fetcher=FakeByteFetcher([]))
    blocks = await deliver(flow, ExtractedParams(), ctx)
    assert isinstance(blocks[0], FileCard)
    assert ctx.byte_fetcher.calls == 0  # bytes already in hand
    assert cache.get(selection_cache_key(flow.intent, ExtractedParams()), now=ctx.now) == PDF


async def test_password_hint_flows_to_file_card():
    flow = FakeFlow(intent=Intent.report_tax, title="Tax Report", password_hint="PAN", generate_results=[ReportUrl("u")])
    blocks = await deliver(flow, ExtractedParams(fy="2024-2025"), make_ctx(fetcher=FakeByteFetcher([PDF])))
    assert isinstance(blocks[0], FileCard) and blocks[0].password_hint == "PAN"


async def test_excel_format_maps_to_xlsx():
    flow = FakeFlow(intent=Intent.report_tax, title="Tax Report", generate_results=[ReportUrl("u", ReportFormat.excel)])
    params = ExtractedParams(fy="2024-2025", report_format=ReportFormat.excel)
    xlsx = b"PK\x03\x04" + b"\x00" * 5000
    blocks = await deliver(flow, params, make_ctx(fetcher=FakeByteFetcher([xlsx])))
    assert isinstance(blocks[0], FileCard)
    assert blocks[0].format == "xlsx" and blocks[0].filename.endswith(".xlsx")


async def test_email_confirmation_masks_registered_email():
    flow = FakeFlow(intent=Intent.report_tax, title="Tax Report", generate_results=[EmailResult(raw_email="SANJAY.HARSHA@GMAIL.COM", sent=(ReportFormat.pdf,))])
    blocks = await deliver(flow, ExtractedParams(fy="2024-2025"), make_ctx())
    assert isinstance(blocks[0], Bubble)
    assert "san***.harsha@gmail.com" in blocks[0].text
    assert "SANJAY.HARSHA" not in blocks[0].text and "sanjay.harsha" not in blocks[0].text


async def test_ec12_partial_dual_format_email_failure():
    flow = FakeFlow(intent=Intent.report_tax, title="Tax Report", generate_results=[EmailResult(raw_email="SANJAY.HARSHA@GMAIL.COM", sent=(ReportFormat.pdf,), failed=(ReportFormat.excel,))])
    blocks = await deliver(flow, ExtractedParams(fy="2024-2025"), make_ctx())
    assert isinstance(blocks[0], Bubble)
    assert blocks[0].text == "Your PDF is on its way to san***.harsha@gmail.com, but the Excel didn't go through."
    assert isinstance(blocks[1], ChipRow)
    assert [c.label for c in blocks[1].chips] == ["↺ Retry Excel", "📊 Get Excel here", "🎫 Raise a ticket"]


def test_mask_email_rules():
    assert mask_email("SANJAY.HARSHA@GMAIL.COM") == "san***.harsha@gmail.com"
    assert mask_email("sanjayharsha@gmail.com") == "san***@gmail.com"
