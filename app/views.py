import base64
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from time import perf_counter, sleep, time
from zoneinfo import ZoneInfo

import plotly.graph_objects as go
import streamlit as st

from app.presentation import (
    business_date,
    compact_money,
    ist_timestamp,
    label,
    percent,
)
from app.presentation import (
    html_text as esc,
)
from milaan import analytics, live
from milaan.config import ROOT
from milaan.db import connect, current_scope, query, scope
from milaan.demo import is_running, reset_demo
from milaan.explain import generate_explanations, rupees
from milaan.pipeline import PASSES, recon

PAGES = {
    "Today's close": ":material/dashboard:",
    "Exceptions queue": ":material/format_list_bulleted:",
    "Exception detail": ":material/compare_arrows:",
    "Accuracy & performance": ":material/monitoring:",
    "How it works": ":material/account_tree:",
}


@st.cache_data(ttl=5)
def cached_summary(scope_name="month"):
    with scope(scope_name):
        return analytics.summary()


@st.cache_data(ttl=5)
def cached_read(sql, params, scope_name):
    with scope(scope_name):
        return query(sql, params)


def read(sql, params=None):
    return cached_read(sql, params, current_scope())


def navigate(page, identifier=None):
    st.session_state["workspace"] = page
    if page == "Exceptions queue":
        st.session_state["queue_revision"] = st.session_state.get("queue_revision", 0) + 1
    if identifier is not None:
        st.session_state["exception_id"] = identifier
        st.session_state["detail_identifier"] = identifier


def markup(text):
    st.html(text)


def metrics(items):
    cards = []
    for title, value, note, tone, full in items:
        if title == "Loan":
            tone = tone + " identifier"
        cards.append(
            f'<div class="metric-card" title="{esc(full)}"><div class="metric-label">{esc(title)}</div><div class="metric-value {tone}">{esc(value)}</div><div class="metric-note">{esc(note)}</div></div>'
        )
    markup('<div class="metric-grid">' + "".join(cards) + "</div>")


def section(title, note=""):
    markup(
        f'<div class="section-head"><span class="section-title">{esc(title)}</span><span class="section-note">{esc(note)}</span></div>'
    )


def request_run():
    st.session_state["run_requested"] = True


def header(title, subtitle, data, action=None):
    date = business_date(data.get("AS_OF_DATE"))
    markup(
        f'<div class="workspace-bar"><div class="breadcrumb">Collections <span style="margin:0 9px;color:#b5c2b7">/</span> Reconciliation</div><div class="workspace-meta"><span>Business date · {date}</span><span class="chip green"><span class="online-dot"></span>Exasol connected</span><span class="chip">Synthetic data</span></div></div>'
    )
    if action:
        left, right = st.columns([3, 1.2], vertical_alignment="center")
        with left:
            st.title(title)
            markup(f'<p class="hero-sub">{esc(subtitle)}</p>')
        with right:
            clicked = st.button(
                action,
                type="primary",
                width="stretch",
                key="run_recon",
                icon=":material/play_arrow:",
                disabled=is_running() or st.session_state.get("run_requested", False),
                on_click=request_run,
            )
        return clicked
    st.title(title)
    markup(f'<p class="hero-sub">{esc(subtitle)}</p>')
    return False


def render():
    st.set_page_config(
        page_title="Milaan · Collections workspace",
        page_icon="₹",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.html(ROOT / "app/style.css")
    font = base64.b64encode((ROOT / "docs/brand/fonts/InterVariable.woff2").read_bytes()).decode()
    markup(
        f'<style>@font-face{{font-family:Inter;font-style:normal;font-weight:100 900;font-display:swap;src:url(data:font/woff2;base64,{font}) format("woff2");}}</style>'
    )
    if st.query_params.get("present") == "1" or os.getenv("MILAAN_PRESENT") == "1":
        markup(
            '<style>[data-testid="stHeader"], [data-testid="stDecoration"], [data-testid="stSidebarHeader"], [data-testid="stSidebarResizeHandle"], [data-testid="stSidebarCollapseButton"]{display:none!important;} html{font-size:17.6px;} [data-testid="stMainBlockContainer"]{padding-top:1.7rem;} .metric-value{font-size:34px;} .hero-sub{font-size:15.4px;} .metric-card{padding:24px 20px;}</style>'
        )
    page = st.session_state.setdefault("workspace", "Today's close")
    if page not in PAGES:
        page = "Today's close"
        st.session_state["workspace"] = page
    with st.sidebar:
        logo = (ROOT / "docs/brand/logo.svg").read_text().replace("#20352f", "#effff5")
        markup(
            '<div class="brand" style="display:block">'
            + '<img alt="Milaan" style="width:200px;height:55px" src="data:image/svg+xml;base64,'
            + base64.b64encode(logo.encode()).decode()
            + '">'
            + '<div class="brand-sub">Collections workspace</div></div><div class="nav-label">Workspace</div>'
        )
        for name, icon in PAGES.items():
            st.button(
                name,
                icon=icon,
                width="stretch",
                type="primary" if name == page else "secondary",
                on_click=navigate,
                args=(name,),
                key="nav_" + name,
            )
        st.divider()
        selected_mode = st.radio(
            "Reconciliation scope",
            ["Today's close", "Full month (10M)"],
            index=1,
            key="reconciliation_mode",
        )
        if selected_mode == "Today's close":
            st.date_input("Close date", value=date(2026, 10, 14), key="close_date")
        markup(
            '<div class="sidebar-account"><strong>Sahyog Finance Ltd</strong><br>Collections &amp; daily close<br><span style="color:#87a995">Demonstration workspace</span></div>'
        )
        now = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%d %b · %H:%M IST")
        markup(
            f'<div class="sidebar-footer" style="margin-top:24px"><span class="online-dot"></span>Exasol Personal<br>Evidence-backed explanations<br><span style="color:#708f7e">{now}</span></div>'
        )
    try:
        scope_name = "day" if selected_mode == "Today's close" else "month"
        try:
            data = cached_summary(scope_name)
        except Exception:
            if scope_name != "day":
                raise
            from milaan.daily import initialise

            with scope("month"):
                initialise()
            data = cached_summary(scope_name)
        if not data:
            if scope_name == "day" and cached_summary("month"):
                with scope("day"):
                    triggered = header(
                        "Today's close",
                        "Prepare the prior close, then match today's arrivals against its open items.",
                        {"AS_OF_DATE": st.session_state["close_date"]},
                        "Run today's close",
                    )
                    triggered = st.session_state.pop("run_requested", False) or triggered
                    markup(
                        '<div class="empty-state"><strong>Your source files are ready</strong>The first daily run prepares prior-date open items. Later closes process new arrivals and carry the unresolved items forward.</div>'
                    )
                    if triggered:
                        run_reconciliation()
                return
            header(
                "Your collections workspace",
                "Connect your source files to begin a daily close.",
                {},
            )
            markup(
                '<div class="empty-state"><strong>No dataset loaded</strong>Set up the synthetic demonstration to see receipts, settlements and exceptions.</div>'
            )
            with st.expander("Setup instructions"):
                st.code("make setup data load recon explain")
            return
        views = {
            "Today's close": home,
            "Exceptions queue": queue,
            "Exception detail": exception_detail,
            "Accuracy & performance": accuracy,
            "How it works": how,
        }
        with scope(scope_name):
            views[page](data)
    except Exception as error:
        markup(
            '<div class="empty-state"><strong>Let’s reconnect your workspace</strong>Exasol is not responding yet. Start the local database, then refresh to continue.</div>'
        )
        st.code("bash scripts/exasol-local.sh start")
        if st.button("Refresh workspace", icon=":material/refresh:"):
            st.cache_data.clear()
            st.rerun()
        with st.expander("Connection diagnostics"):
            st.code(str(error))


def live_panel(snapshot, elapsed):
    completed = {r["PASS_NAME"]: r for r in snapshot.get("PASSES", [])}
    rows = []
    for index, (name, _) in enumerate(PASSES, 1):
        record = completed.get(name)
        state = (
            "done" if record else "running" if snapshot.get("CURRENT_PASS") == name else "waiting"
        )
        note = f"{record['LINKS_ADDED']:,} links found" if record else state.capitalize()
        seconds = f"{record['SECONDS']:.2f}s" if record else ""
        rows.append(
            f'<div class="live-pass {state}"><span class="state">{"✓" if record else index}</span><div><strong>{esc(label(name))}</strong><small>{note}</small></div><span class="seconds">{seconds}</span></div>'
        )
    pct = snapshot.get("MEMBERS", 0) / max(snapshot.get("SOURCE_ROWS", 1), 1)
    matched_label = percent(pct) if snapshot else "—"
    amount = compact_money(snapshot.get("OPEN_PAISE", 0)) if snapshot else "—"
    return (
        '<div class="batch-comparison" style="grid-template-columns:1.4fr 1fr"><div class="live-panel" id="pass-list">'
        + "".join(rows)
        + f'</div><div class="live-panel"><div class="live-caption">Measured progress inside Exasol</div><div class="metric-label" style="margin-top:45px">Automatically grouped</div><div class="metric-value green" id="live-matched">{matched_label}</div><div class="metric-label" style="margin-top:45px">Unreconciled receipts</div><div class="metric-value amber" id="live-unreconciled">{amount}</div><p class="live-caption" style="margin-top:45px">Matching, scoring and validation run in the database.<br>Updates read the committed audit snapshots.</p></div></div>'
    )


def run_reconciliation():
    started = perf_counter()
    scope_name = current_scope()
    close_day = str(st.session_state.get("close_date", date(2026, 10, 14)))
    clock = st.empty()
    panel = st.empty()
    phase_note = st.empty()
    previous_id = live.snapshot().get("RUN_ID")
    previous_panel = None

    def work():
        with scope(scope_name):
            if scope_name == "day":
                from milaan.daily import recon_day

                result = recon_day(close_day)
            else:
                result = recon()
            generate_explanations()
            return result

    with connect() as reader, ThreadPoolExecutor(max_workers=1) as executor:
        task = executor.submit(work)
        while not task.done():
            snapshot = live.snapshot(reader)
            if snapshot.get("RUN_ID") == previous_id:
                snapshot = {}
            elapsed = (
                (time() * 1000 - snapshot["STARTED_EPOCH_MS"]) / 1000
                if snapshot
                else perf_counter() - started
            )
            if snapshot.get("STATUS") == "COMPLETE":
                elapsed = snapshot["ELAPSED_SECONDS"]
                phase_note.caption("Matching complete · preparing evidence-backed explanations")
            clock.html(
                f'<div class="live-timer" id="live-timer" style="font-size:48px;margin:4px 0 12px">{elapsed:.1f}<span style="font-size:20px;color:#6d7c75;letter-spacing:0;margin-left:8px;font-weight:400">s elapsed</span></div>'
            )
            panel_key = (
                snapshot.get("RUN_ID"),
                snapshot.get("CURRENT_PASS"),
                snapshot.get("MEMBERS"),
                snapshot.get("STATUS"),
                len(snapshot.get("PASSES", [])),
            )
            if panel_key != previous_panel:
                panel.html(live_panel(snapshot, elapsed))
                previous_panel = panel_key
            sleep(0.35)
        result = task.result()
    st.cache_data.clear()
    st.session_state["completed_run"] = result["run_id"]
    st.toast("Reconciliation complete. Your exceptions are ready.", icon=":material/check_circle:")
    st.rerun()


def pass_timings(run_id):
    return read(
        "SELECT pass_name,seconds,links_added,profile_json FROM MILAAN_AUDIT.PASS_TIMING WHERE run_id={id!s}",
        {"id": run_id},
    )


def bar_chart(rows, field="LINKS_ADDED", unit="Receipt links"):
    names = [name for name, _ in PASSES if name != "CLASSIFY"]
    by_name = {r["PASS_NAME"]: r for r in rows}
    values = [float(by_name[name][field]) for name in names if name in by_name]
    labels = [label(name) for name in names if name in by_name]
    chart = go.Figure(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            marker_color=["#1c9671", "#50b38b", "#a2ccb3", "#acc6b0", "#c4d6bf", "#d6e1cc"][
                : len(values)
            ],
            text=[f"{v:,.0f}" if field == "LINKS_ADDED" else f"{v:.2f}s" for v in values],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{y}<br>%{x:,.0f} " + unit + "<extra></extra>",
        )
    )
    chart.update_layout(
        height=260,
        margin=dict(l=0, r=75, t=5, b=24),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        font=dict(family="Inter", size=12, color="#6b7c6f"),
        xaxis=dict(showgrid=True, gridcolor="#eff2ec", zeroline=False, title=None),
        yaxis=dict(autorange="reversed", showgrid=False),
        bargap=0.44,
    )
    st.plotly_chart(chart, width="stretch", config={"displayModeBar": False})


def home(data):
    triggered = header(
        "Today's close" if current_scope() == "day" else "Full month close",
        "A clear view of your collections. Match the receipts; investigate the differences.",
        data,
        "Run today's close" if current_scope() == "day" else "Run reconciliation (full month)",
    )
    triggered = st.session_state.pop("run_requested", False) or triggered
    body = st.empty()
    if triggered:
        body.empty()
        with body.container():
            run_reconciliation()
        return
    with body.container():
        with st.container(key="home_results"):
            home_content(data)


def home_content(data):
    run = data.get("RUN")
    if is_running():
        st.info("A reconciliation is running. The run button unlocks when it finishes.")
    elif run and run["STATUS"] == "FAILED":
        st.warning("The last run stopped before completion. Reset the demo and retry.")
    if run and st.session_state.get("completed_run") == run["RUN_ID"]:
        st.success("Results and evidence-backed explanations are ready.")
    auto = data["MEMBERS"] / data["SOURCE_ROWS"] if data["SOURCE_ROWS"] else 0
    live_data = data.get("LIVE", {})
    pending = live_data.get("OPEN_PAISE", data["OPEN_PAISE"])
    before = live_data.get("BEFORE_PAISE", pending)
    daily = data.get("DAILY", {})
    new_today = sum(daily.get("new_source_counts", {}).values())
    metrics(
        [
            (
                "New records today" if daily else "Source records",
                f"{new_today if daily else data['SOURCE_ROWS']:,}",
                f"{data['SOURCE_ROWS']:,} available through this close"
                if daily
                else "Across four source files",
                "",
                f"{data['SOURCE_ROWS']:,} records",
            ),
            (
                "Automatically grouped",
                percent(auto),
                "Records in validated match groups",
                "green",
                f"{data['MEMBERS']:,} grouped records",
            ),
            (
                "Unreconciled receipts",
                compact_money(pending),
                compact_money(before) + " → " + compact_money(pending),
                "amber",
                rupees(pending),
            ),
            (
                "Exceptions found",
                f"{data['EXCEPTIONS']:,}",
                "Prioritised by impact and age",
                "",
                f"{data['EXCEPTIONS']:,} current exceptions",
            ),
        ]
    )
    status = (
        f"Last run · {run['SECONDS']:.2f}s"
        if run and run["SECONDS"] is not None
        else "Awaiting first reconciliation"
    )
    st.caption(
        status
        + " · Receipts awaiting a match; bank-only differences appear in the exceptions queue."
    )
    if st.button("Reset demo", icon=":material/restart_alt:", disabled=is_running()):
        reset_demo(current_scope(), str(st.session_state.get("close_date", date(2026, 10, 14))))
        st.cache_data.clear()
        st.session_state.pop("completed_run", None)
        st.toast("Demo reset. Source data and review history are retained.")
        st.rerun()
    if data["EXCEPTIONS"] and current_scope() == "month":
        st.button(
            "Review the 37-payment batch",
            on_click=navigate,
            args=("Exception detail", "PG:PG000000000-36"),
            icon=":material/compare_arrows:",
        )
    left, right = st.columns([1.5, 1], gap="medium")
    with left, st.container(border=True, key="panel_home_matching"):
        section("Receipt links by matching pass", "Measured in Exasol")
        rows = pass_timings(run["RUN_ID"]) if run else []
        if rows:
            bar_chart(rows)
        else:
            markup(
                '<div class="empty-state"><strong>Ready for reconciliation</strong>Run the matching passes to see how receipts reconcile.</div>'
            )
        st.caption(
            "One group may link several records. Receipt links and source records use different denominators."
        )
    categories = read(
        'SELECT category,COUNT(*) N FROM MILAAN_RES."EXCEPTION" GROUP BY category ORDER BY N DESC'
    )
    with right, st.container(border=True, key="panel_home_categories"):
        section("Exceptions at a glance", f"{data['EXCEPTIONS']:,} total")
        if categories:
            markup(
                "".join(
                    f'<div class="summary-line"><span class="summary-label">{esc(label(r["CATEGORY"]))}</span><span class="summary-number">{r["N"]:,}</span></div>'
                    for r in categories[:6]
                )
            )
        else:
            st.caption("No unresolved exceptions in this run.")
        st.button(
            "Open exceptions queue",
            icon=":material/arrow_forward:",
            width="stretch",
            on_click=navigate,
            args=("Exceptions queue",),
        )
    with st.container(border=True, key="panel_home_reviews"):
        section("Priority reviews", "Highest impact first")
        rows = analytics.exceptions()[:3]
        if rows:
            columns = st.columns(len(rows), gap="medium")
            for col, row in zip(columns, rows, strict=True):
                with col:
                    tone = "red" if row["RISK_WEIGHT"] >= 5 else "amber"
                    markup(
                        f'<span class="chip {tone}">{esc(label(row["CATEGORY"]))}</span><p style="font-size:23px;font-weight:600;margin:12px 0 4px">{esc(rupees(row["AMOUNT_PAISE"]))}</p><p class="muted">{esc(row["LOAN_ID"])} · {row["AGE_BUSINESS_DAYS"]} business days</p>'
                    )
                    st.button(
                        "Review exception",
                        key="review_" + row["EXCEPTION_ID"],
                        width="stretch",
                        on_click=navigate,
                        args=("Exception detail", row["EXCEPTION_ID"]),
                    )
        else:
            markup(
                '<div class="insight">There are no current exception records. Run reconciliation to refresh the daily close.</div>'
            )


def queue(data):
    header(
        "Exceptions queue",
        "Start with the highest-impact breaks. Select a row to inspect its evidence.",
        data,
    )
    with st.container(border=True, key="panel_queue"):
        filters = st.columns(4, gap="small")
        categories = [
            r["CATEGORY"]
            for r in read('SELECT DISTINCT category FROM MILAAN_RES."EXCEPTION" ORDER BY category')
        ]
        category = filters[0].selectbox(
            "Category",
            ["All"] + categories,
            format_func=lambda x: "All categories" if x == "All" else label(x),
            key="filter_category",
        )
        channel = filters[1].selectbox(
            "Channel", ["All", "UPI", "NACH", "PG", "NEFT"], key="filter_channel"
        )
        age = filters[2].selectbox(
            "Business-day age", ["All", "0–1", "2–3", "4–7", "8+"], key="filter_age"
        )
        amount = filters[3].selectbox(
            "Amount",
            ["All", "Below ₹10,000", "₹10,000–₹25,000", "Above ₹25,000"],
            key="filter_amount",
        )
        signature = (category, channel, age, amount)
        if st.session_state.get("filter_signature") != signature:
            st.session_state["queue_page"] = 1
            st.session_state["filter_signature"] = signature
        page = st.session_state.setdefault("queue_page", 1)
        rows = analytics.exceptions(category, channel, age, amount, (page - 1) * 50)
        section("Priority order", f"Page {page} · up to 50 items")
        if not rows:
            markup(
                '<div class="empty-state"><strong>No exceptions in this view</strong>Try a different category, channel, age or amount filter.</div>'
            )
        else:
            display = [
                {
                    "Exception": r["EXCEPTION_ID"],
                    "Issue": label(r["CATEGORY"]),
                    "Loan": r["LOAN_ID"] or "Unidentified",
                    "Channel": r["CHANNEL"],
                    "Amount": rupees(r["AMOUNT_PAISE"]),
                    "Age": f"{r['AGE_BUSINESS_DAYS']} days",
                    "Review status": {
                        "ACCEPT": "Accepted",
                        "REJECT": "Rejected",
                        "ASSIGN": "Assigned",
                    }.get(r.get("REVIEW_ACTION"), "Not reviewed"),
                }
                for r in rows
            ]
            chosen = st.dataframe(
                display,
                width="stretch",
                height=420,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key=f"queue_table_{signature}_{page}_{st.session_state.get('queue_revision', 0)}",
                column_config={
                    "Exception": st.column_config.TextColumn(width=125),
                    "Issue": st.column_config.TextColumn(width=245),
                    "Loan": st.column_config.TextColumn(width=105),
                    "Channel": st.column_config.TextColumn(width=70),
                    "Amount": st.column_config.TextColumn(width=110),
                    "Age": st.column_config.TextColumn(width=75),
                    "Review status": st.column_config.TextColumn(width=110),
                },
            )
            selected = chosen.selection.rows
            if selected:
                identifier = rows[selected[0]]["EXCEPTION_ID"]
                navigate("Exception detail", identifier)
                st.rerun()
        foot = st.columns([3, 1, 1], gap="small", vertical_alignment="center")
        foot[0].caption("Priority = amount × max(business-day age, 1) × risk weight.")
        if foot[1].button(
            "Previous", width="stretch", disabled=page == 1, icon=":material/chevron_left:"
        ):
            st.session_state["queue_page"] = page - 1
            st.rerun()
        if foot[2].button(
            "Next", width="stretch", disabled=len(rows) < 50, icon=":material/chevron_right:"
        ):
            st.session_state["queue_page"] = page + 1
            st.rerun()
    if rows:
        with st.expander("Open by exception ID"):
            choice = st.selectbox("Select an exception", [r["EXCEPTION_ID"] for r in rows])
            st.button(
                "Open selected exception",
                type="primary",
                on_click=navigate,
                args=("Exception detail", choice),
            )
    markup(
        '<div class="insight">Returned NACH debits and receipts missing from the bank carry a higher risk weight. A review decision is recorded separately from an approved accounting posting.</div>'
    )


def source_card(title, records, category):
    status = "Record found" if records else "No record"
    tone = (
        "green"
        if records
        else ("amber" if title == "Ledger" and category == "MISSING_IN_LEDGER" else "")
    )
    content = f'<div class="evidence-card"><div class="evidence-head">{esc(title)}<span class="chip {tone}">{status}</span></div>'
    if not records:
        text = (
            "This gateway payment has no corresponding receipt in the ledger."
            if title == "Ledger" and category == "MISSING_IN_LEDGER"
            else "This exception has no linked record from this source."
        )
        return (
            content
            + f'<div class="evidence-empty"><strong>{"Receipt missing" if title == "Ledger" and category == "MISSING_IN_LEDGER" else "No linked evidence"}</strong>{esc(text)}</div></div>'
        )
    field_names = {
        "LEDGER_ID": "Receipt ID",
        "LOAN_ID": "Loan",
        "CUSTOMER_NAME": "Customer",
        "AMOUNT_PAISE": "Receipt amount",
        "CREDIT_PAISE": "Bank credit",
        "DEBIT_PAISE": "Bank debit",
        "GROSS_PAISE": "Payment amount",
        "FEE_PAISE": "Gateway fee",
        "GST_ON_FEE_PAISE": "GST on fee",
        "NET_PAISE": "Net payment",
        "BANK_TXN_ID": "Transaction ID",
        "BANK_REF": "Bank reference",
        "PG_PAYMENT_ID": "Payment ID",
        "ORDER_REF": "Loan reference",
        "SETTLEMENT_BATCH_ID": "Settlement batch",
        "SETTLEMENT_UTR": "Settlement reference",
        "NARRATION": "Bank narration",
        "UMRN": "Mandate reference",
    }
    content += '<div class="evidence-body">'
    for record in records:
        for key, value in record.items():
            if key.endswith("PAISE"):
                value = rupees(value)
            elif key.endswith("DATE"):
                value = business_date(value)
            attention = (
                key in ("STATUS", "RETURN_REASON") and category == "NACH_BOUNCE_MISPOSTED"
            ) or (key in ("AMOUNT_PAISE", "CREDIT_PAISE") and category == "PARTIAL_PAYMENT")
            content += f'<div class="field {"attention" if attention else ""}"><div class="field-label">{esc(field_names.get(key, key.replace("_", " ").capitalize()))}</div><div class="field-value">{esc(value)}</div></div>'
    return content + "</div></div>"


def exception_detail(data):
    header(
        "Exception detail",
        "Compare the source evidence, understand the break and record your review.",
        data,
    )
    top = st.columns([1, 3], vertical_alignment="center")
    top[0].button(
        "Back to queue",
        icon=":material/arrow_back:",
        on_click=navigate,
        args=("Exceptions queue",),
        width="stretch",
    )
    if "detail_identifier" not in st.session_state:
        st.session_state["detail_identifier"] = st.session_state.get("exception_id", "")
    identifier = top[1].text_input(
        "Exception ID",
        key="detail_identifier",
        label_visibility="collapsed",
        placeholder="Choose an exception from the queue",
    )
    if not identifier:
        markup(
            '<div class="empty-state"><strong>Select an exception to get started</strong>Open the queue and click a row to compare its source records.</div>'
        )
        return
    row = analytics.detail(identifier)
    if not row:
        st.warning(
            "This exception is not in the current run. Return to the queue to choose a current item."
        )
        return
    evidence = json.loads(row["EVIDENCE"])
    st.subheader(label(row["CATEGORY"]))
    metrics(
        [
            (
                "Amount to review",
                rupees(row["AMOUNT_PAISE"]),
                "INR · exact amount",
                "amber",
                rupees(row["AMOUNT_PAISE"]),
            ),
            (
                "Loan",
                row["LOAN_ID"] or "Unidentified",
                row["CHANNEL"] + " collection",
                "",
                row["LOAN_ID"],
            ),
            (
                "Age",
                f"{row['AGE_BUSINESS_DAYS']} days",
                "Business days outstanding",
                "",
                row["AGE_BUSINESS_DAYS"],
            ),
            (
                "Review priority",
                "High risk" if row["RISK_WEIGHT"] >= 5 else "Needs review",
                f"Risk weight · {row['RISK_WEIGHT']}",
                "",
                row["RISK_WEIGHT"],
            ),
        ]
    )
    batch = analytics.batch_evidence(evidence) if row["CATEGORY"] == "MISSING_IN_LEDGER" else {}
    if batch:
        section("One settlement. Every receipt.", "PayFast · verified source evidence")
        markup(f"""<div class="batch-comparison">
            <div class="evidence-card"><div class="evidence-head">Bank credit</div><div class="evidence-body"><div class="batch-number">{rupees(batch["BANK_CREDIT_PAISE"])}</div><div class="field"><div class="field-label">Value date</div><div class="field-value">{business_date(batch["VALUE_DATE"])}</div></div><div class="field"><div class="field-label">Bank reference</div><div class="field-value">{esc(batch["BANK_REF"])}</div></div></div></div>
            <div class="evidence-card"><div class="evidence-head">Gateway batch</div><div class="evidence-body"><div class="batch-number">{batch["PAYMENT_COUNT"]} payments</div><div class="field"><div class="field-label">Gross collected</div><div class="field-value">{rupees(batch["GROSS_PAISE"])}</div></div><div class="field"><div class="field-label">Settlement batch</div><div class="field-value">{esc(batch["BATCH_ID"])}</div></div></div></div>
            <div class="evidence-card"><div class="evidence-head">Ledger receipts</div><div class="evidence-body"><div class="batch-number">{batch["MATCHED_RECEIPTS"]} matched</div><div class="missing-receipt"><strong>Receipt missing</strong><br>{esc(row["LOAN_ID"])}<br>{rupees(row["AMOUNT_PAISE"])} · {row["CHANNEL"]}</div></div></div>
            </div>""")
        equation = [
            (batch["GROSS_PAISE"], "Gross"),
            (batch["FEE_PAISE"], "Fees"),
            (batch["GST_PAISE"], "GST"),
        ]
        if batch["REFUND_PAISE"]:
            # Gross includes negative refund rows; add them back for the collection total.
            equation[0] = (batch["GROSS_PAISE"] + batch["REFUND_PAISE"], "Gross collections")
            equation.append((batch["REFUND_PAISE"], "Refunds"))
        pieces = []
        for index, (amount, title) in enumerate(equation):
            if index:
                pieces.append('<span class="operator">−</span>')
            pieces.append(f"<div><strong>{rupees(amount)}</strong><small>{title}</small></div>")
        pieces.append(
            f'<span class="operator">=</span><div><strong style="color:#158568">{rupees(batch["NET_PAISE"])}</strong><small>Bank credit</small></div>'
        )
        markup(
            '<div class="settlement-equation" id="settlement-equation">'
            + "".join(pieces)
            + "</div>"
        )
    explanation = row["EXPLANATION"] or row["SUGGESTED_ACTION"]
    markup(
        f'<div class="explanation" id="explanation-callout"><div class="explanation-label">What the evidence tells us</div>{esc(explanation)}</div>'
    )
    difference = {
        "MISSING_IN_LEDGER": "The bank batch reconciles, but this gateway payment is missing from the ledger.",
        "PARTIAL_PAYMENT": f"The ledger shows {rupees(evidence['amount_paise'])}; the bank candidate contains {rupees(evidence.get('bank_paise'))}.",
        "NACH_BOUNCE_MISPOSTED": "The ledger status is PAID, while the NACH return reports a failed collection.",
        "NAME_MISMATCH": "The candidate amount agrees, but payer or reference checks did not support an automatic match.",
    }.get(row["CATEGORY"])
    if difference:
        markup(f'<div class="difference">{esc(difference)}</div>')
    section("Source comparison", "Amounts shown in rupees")
    records = analytics.evidence_records(evidence)
    # Two columns keep long references readable on a laptop; narrow screens stack them.
    for names in () if batch else (("Ledger", "Bank"), ("Gateway", "NACH")):
        columns = st.columns(2, gap="medium")
        for column, name in zip(columns, names, strict=True):
            with column:
                markup(source_card(name, records.get(name, []), row["CATEGORY"]))
    if batch:
        with st.expander(f"Inspect all {batch['PAYMENT_COUNT']} gateway payments", expanded=False):
            st.dataframe(
                [
                    {
                        "Payment": p["PG_PAYMENT_ID"],
                        "Loan": p["LOAN_ID"],
                        "Amount": rupees(p["GROSS_PAISE"]),
                        "Receipt": p["RECEIPT_STATUS"],
                    }
                    for p in batch["PAYMENTS"]
                ],
                hide_index=True,
                width="stretch",
                height=350,
            )
        with st.expander("Bank narration and original source records"):
            st.json(records)
    with st.container(border=True, key="panel_decision"):
        section("Record a decision", "Saved to the Exasol audit trail")
        st.caption(
            "Accepting a recommendation records your review. Posting or reversing a real receipt requires a separate accounting approval."
        )
        with st.form("review_decision", clear_on_submit=False):
            left, right = st.columns(2)
            analyst = left.text_input("Analyst", value="Hemanth Chilakala")
            assignee = right.text_input("Assign to", placeholder="Collections owner")
            note = st.text_area(
                "Decision note",
                placeholder="Add the checks you performed or the next step.",
                height=90,
            )
            buttons = st.columns(3)
            accept = buttons[0].form_submit_button(
                "Accept", type="primary", width="stretch", icon=":material/check:"
            )
            reject = buttons[1].form_submit_button(
                "Reject", width="stretch", icon=":material/close:"
            )
            assign = buttons[2].form_submit_button(
                "Assign", width="stretch", icon=":material/person_add:"
            )
            action = "ACCEPT" if accept else "REJECT" if reject else "ASSIGN" if assign else None
            if action:
                if not analyst.strip():
                    st.warning("Enter the analyst name before saving a decision.")
                elif action == "ASSIGN" and not assignee.strip():
                    st.warning("Enter an assignee before assigning this exception.")
                else:
                    identifier_saved = analytics.decision(
                        identifier, action, analyst, assignee, note
                    )
                    st.toast(
                        "Decision saved to Exasol · " + identifier_saved[:8],
                        icon=":material/check_circle:",
                    )
                    st.success("Decision saved to the Exasol audit trail.")
        audit = query(
            "SELECT decision_action,analyst,assignee,note,CONVERT_TZ(created_at,DBTIMEZONE,'Asia/Kolkata') created_at FROM MILAAN_AUDIT.DECISION WHERE exception_id={id!s} AND run_id={run!s} ORDER BY created_at DESC LIMIT 10",
            {"id": identifier, "run": row["RUN_ID"]},
        )
        if audit:
            section("Recent review activity")
            st.dataframe(
                [
                    {
                        "Decision": r["DECISION_ACTION"].capitalize(),
                        "Analyst": r["ANALYST"],
                        "Assigned to": r["ASSIGNEE"] or "—",
                        "Note": r["NOTE"] or "—",
                        "Time": ist_timestamp(r["CREATED_AT"]),
                    }
                    for r in audit
                ],
                hide_index=True,
                width="stretch",
            )
    with st.expander("Structured evidence & references"):
        st.json(evidence)


def accuracy(data):
    header(
        "Accuracy & performance",
        "Measured results with known answers. Inspect correctness alongside execution time.",
        data,
    )
    scores = read("SELECT * FROM MILAAN_RES.SCORE ORDER BY break_type")
    overall = next((r for r in scores if r["BREAK_TYPE"] == "OVERALL"), None)
    if not overall:
        markup(
            '<div class="empty-state"><strong>No completed measurements</strong>Run reconciliation from the daily close to score the matching results.</div>'
        )
        return
    rows = pass_timings(overall["RUN_ID"])
    run = data.get("RUN")
    metrics(
        [
            (
                "Link precision",
                percent(overall["PRECISION_VALUE"], 3),
                "Correct links / predicted links",
                "green",
                percent(overall["PRECISION_VALUE"], 3),
            ),
            (
                "Link recall",
                percent(overall["RECALL_VALUE"], 3),
                "Found links / expected links",
                "green",
                percent(overall["RECALL_VALUE"], 3),
            ),
            (
                "False matches",
                f"{overall['FALSE_POSITIVE']:,}",
                "Incorrect predicted links",
                "",
                overall["FALSE_POSITIVE"],
            ),
            (
                "Reconciliation time",
                f"{run['SECONDS']:.2f}s" if run and run["SECONDS"] is not None else "—",
                "Includes scoring and validation",
                "",
                run["SECONDS"] if run else "",
            ),
        ]
    )
    markup(
        '<div class="insight">Measured on synthetic data with known answers. Matching uses source evidence; separate ground truth scores the resulting links. Compare normal, blind and hard cases below.</div>'
    )
    with st.container(border=True, key="panel_accuracy"):
        validation_path = ROOT / "docs/validation_results.json"
        if validation_path.exists():
            from scripts.validate_holdout import comparison_rows

            section("Normal, blind and hard", "Unchanged matching rules · 1M records each")
            st.dataframe(
                comparison_rows(json.loads(validation_path.read_text())),
                hide_index=True,
                width="stretch",
            )
            st.caption(
                "Blind seed 20261025 uses unseen, randomised break rates. Hard mode adds ambiguous references, longer delays, extra split transfers and bank reversals."
            )
        section("Accuracy by scenario", "— = no expected or predicted links")
        st.dataframe(
            [
                {
                    "Scenario": label(r["BREAK_TYPE"]),
                    "Correct links": r["TRUE_POSITIVE"],
                    "False links": r["FALSE_POSITIVE"],
                    "Missed links": r["FALSE_NEGATIVE"],
                    "Precision": percent(r["PRECISION_VALUE"], 3),
                    "Recall": percent(r["RECALL_VALUE"], 3),
                }
                for r in scores
                if r["BREAK_TYPE"] != "OVERALL"
            ],
            hide_index=True,
            width="stretch",
            height=430,
            column_config={"Scenario": st.column_config.TextColumn(width="large")},
        )
    with st.container(border=True, key="panel_performance"):
        section("Execution by pass", "Wall-clock time")
        order = {name: i for i, (name, _) in enumerate(PASSES)}
        rows = sorted(rows, key=lambda r: order.get(r["PASS_NAME"], 99))
        st.dataframe(
            [
                {
                    "Pass": label(r["PASS_NAME"]),
                    "Time": f"{r['SECONDS']:.2f}s",
                    "Receipt links": r["LINKS_ADDED"],
                }
                for r in rows
            ],
            hide_index=True,
            width="stretch",
        )
    with st.expander("Exasol's execution profiling"):
        selected = (
            st.selectbox("Inspect a pass", [r["PASS_NAME"] for r in rows], format_func=label)
            if rows
            else None
        )
        record = next((r for r in rows if r["PASS_NAME"] == selected), None)
        if record:
            st.dataframe(
                json.loads(record["PROFILE_JSON"] or "[]"), hide_index=True, width="stretch"
            )
    st.caption(
        "Source membership is validated against conflicting match groups. Batch and split relationships share one group. Explanation generation and profiling flush are timed separately."
    )


def how(data):
    header(
        "How Milaan works",
        "Four source files become one evidence-backed reconciliation workflow.",
        data,
    )
    markup(
        '<div class="process-grid"><div class="process-card"><div class="process-step">01 / Bring the sources together</div><strong>Ledger, bank, gateway & NACH</strong><p>Seeded synthetic files are bulk-imported into Exasol. References, names and dates are normalised with SQL.</p></div><div class="process-card"><div class="process-step">02 / Reconcile inside Exasol</div><strong>Seven explainable passes</strong><p>SQL joins, windows and database-side scripts identify unique matches. Unresolved records become prioritised exceptions.</p></div><div class="process-card"><div class="process-step">03 / Review with context</div><strong>Evidence, decision & audit</strong><p>The analyst sees linked source records and a deterministic explanation, then records a review or assigns an owner.</p></div></div>'
    )
    descriptions = {
        "EXACT": "A unique reference, amount and value date agree.",
        "PG_BATCH": "Gateway net amounts sum to a unique bank credit; gross payments agree with ledger receipts.",
        "FEE_AWARE": "The payment less fees and GST agrees with the net bank settlement.",
        "TOLERANT": "Loan, amount and reference suffix agree within three business days.",
        "FUZZY": "Blocked candidates pass name and reference similarity thresholds.",
        "SPLIT_MERGE": "One unique subset of two or three credits equals a receipt. Groups are capped at 12 candidates.",
        "CLASSIFY": "Remaining records receive a category, business-day age, risk weight and suggested action.",
    }
    with st.container(border=True, key="panel_sequence"):
        section("The matching sequence", "Only unmatched keys enter the next pass")
        markup(
            "".join(
                f'<div class="pass-row"><span class="pass-index">{i:02}</span><strong>{esc(label(name))}</strong><span>{esc(descriptions[name])}</span></div>'
                for i, (name, _) in enumerate(PASSES, 1)
            )
        )
    left, right = st.columns(2, gap="medium")
    with left, st.container(border=True, key="panel_trust"):
        section("Why the result is traceable")
        st.write(
            "Every match carries a rule and evidence. The final conflict check rejects source records assigned to different groups. Review decisions retain the reconciliation run, analyst, note and timestamp."
        )
    with right, st.container(border=True, key="panel_platform"):
        section("Where the work happens")
        st.write(
            "Exasol performs imports, normalisation, matching, explanations and scoring. Python orchestrates the workflow; the dashboard retrieves aggregates and small result pages."
        )
    markup(
        '<div class="insight">All data is synthetic, generated by generator/. No real customer, bank or employer data is used. Explanations are deterministic templates inside Exasol; no external inference API is required.</div>'
    )
