import json
import queue as thread_queue
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from time import perf_counter, sleep
from zoneinfo import ZoneInfo

import plotly.express as px
import streamlit as st

from milaan import analytics
from milaan.db import query
from milaan.explain import generate_explanations, rupees
from milaan.pipeline import recon


@st.cache_data(ttl=5)
def cached_summary():
    return analytics.summary()


def render():
    st.set_page_config(page_title="Milaan · Daily close", page_icon="₹", layout="wide")
    st.markdown(
        "<style>.block-container{padding-top:2rem;max-width:1500px} [data-testid=stMetric]{background:white;padding:18px;border:1px solid #e1e7ec;border-radius:12px} h1{letter-spacing:-.03em} .stButton button{border-radius:8px}</style>",
        unsafe_allow_html=True,
    )
    st.sidebar.title("Milaan")
    st.sidebar.caption("SAHYOG FINANCE LTD\n\nReconciliation workspace")
    page = st.sidebar.radio(
        "Workspace",
        [
            "Today's close",
            "Exceptions queue",
            "Exception detail",
            "Accuracy & performance",
            "How it works",
        ],
    )
    st.sidebar.divider()
    st.sidebar.caption("Synthetic demonstration data\n\nExasol Personal · no API key")
    st.sidebar.caption(datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%d %b %Y · %H:%M IST"))
    try:
        data = cached_summary()
        if not data:
            st.info("Load synthetic data with make data and make load to begin.")
            return
        if page == "Today's close":
            home(data)
        elif page == "Exceptions queue":
            queue()
        elif page == "Exception detail":
            exception_detail()
        elif page == "Accuracy & performance":
            accuracy(data)
        else:
            how()
    except Exception as error:
        st.error(
            "The database operation could not complete. Check Exasol with scripts/exasol-local.sh info, then retry."
        )
        with st.expander("Technical details"):
            st.code(str(error))


def home(data):
    st.caption("DAILY CLOSE / COLLECTIONS")
    st.title("Close the books with confidence")
    st.write(
        "Reconcile receipts across the ledger, bank, gateway and NACH returns. Review the money that needs attention."
    )
    columns = st.columns(5)
    values = [
        ("Source records", f"{data['SOURCE_ROWS']:,}"),
        ("Auto-matched", f"{100 * data['MEMBERS'] / data['SOURCE_ROWS']:.2f}%"),
        ("Exception exposure", rupees(data["OPEN_PAISE"])),
        ("Exceptions", f"{data['EXCEPTIONS']:,}"),
        (
            "Last run",
            f"{data['RUN']['SECONDS']:.2f}s"
            if data["RUN"] and data["RUN"]["SECONDS"]
            else "Not run",
        ),
    ]
    for column, (label, value) in zip(columns, values, strict=True):
        column.metric(label, value)
    st.caption(
        f"Four source files · synthetic business date {data['AS_OF_DATE']} · amounts in INR. Exception exposure includes accounting breaks; it is not a cash balance."
    )
    st.divider()
    if st.session_state.get("completed_run"):
        st.success(
            "Results and evidence-backed explanations are ready. Open the exceptions queue to review priority items."
        )
    if data.get("RUN") and data["RUN"]["STATUS"] != "COMPLETE":
        st.warning(
            f"The latest run is {data['RUN']['STATUS'].lower()}. Current results may be incomplete; run reconciliation to finish a close."
        )
    if st.button("Run reconciliation", type="primary", key="run_recon"):
        start = perf_counter()
        progress = st.status("Matching inside Exasol…", expanded=True)
        clock = st.empty()

        events = thread_queue.Queue()

        def update(name, seconds, count):
            if seconds is None:
                progress.write(f"{name.replace('_', ' ').title()} · running")
            else:
                progress.write(
                    f"{name.replace('_', ' ').title()} · {count:,} receipt links · {seconds:.2f}s"
                )

        with ThreadPoolExecutor(max_workers=1) as executor:
            task = executor.submit(recon, lambda *event: events.put(event))
            while not task.done():
                clock.metric("Elapsed time", f"{perf_counter() - start:.1f}s")
                while not events.empty():
                    update(*events.get())
                sleep(0.25)
            while not events.empty():
                update(*events.get())
            result = task.result()
        clock.metric("Elapsed time", f"{result['seconds']:.2f}s")
        generate_explanations()
        progress.update(
            label=f"Reconciliation complete · {result['seconds']:.2f}s",
            state="complete",
            expanded=True,
        )
        st.cache_data.clear()
        st.session_state["completed_run"] = result
        st.rerun()
    run = data.get("RUN")
    if run:
        rows = query(
            "SELECT pass_name,links_added,seconds FROM MILAAN_AUDIT.PASS_TIMING WHERE run_id={run!s}",
            {"run": run["RUN_ID"]},
        )
        if rows:
            st.subheader("How receipts matched")
            st.plotly_chart(
                px.bar(
                    rows,
                    x="PASS_NAME",
                    y="LINKS_ADDED",
                    color="PASS_NAME",
                    color_discrete_sequence=[
                        "#0f766e",
                        "#14b8a6",
                        "#5eead4",
                        "#334155",
                        "#94a3b8",
                        "#f59e0b",
                    ],
                    labels={"PASS_NAME": "Pass", "LINKS_ADDED": "Receipt links"},
                ),
                width="stretch",
            )
    st.info(
        "High-risk first: returned NACH debits and receipts missing from the bank receive a higher priority weight."
    )


def queue():
    st.caption("REVIEW / PRIORITY QUEUE")
    st.title("Focus on the breaks that matter")
    filters = st.columns(4)
    categories = [
        r["CATEGORY"]
        for r in query('SELECT DISTINCT category FROM MILAAN_RES."EXCEPTION" ORDER BY category')
    ]
    category = filters[0].selectbox("Category", ["All"] + categories)
    channel = filters[1].selectbox("Channel", ["All", "UPI", "NACH", "PG", "NEFT"])
    age = filters[2].selectbox("Business-day age", ["All", "0–1", "2–3", "4–7", "8+"])
    amount = filters[3].selectbox(
        "Amount", ["All", "Below ₹10,000", "₹10,000–₹25,000", "Above ₹25,000"]
    )
    page = st.number_input("Page", min_value=1, value=1, step=1)
    rows = analytics.exceptions(category, channel, age, amount, (page - 1) * 50)
    st.caption(
        "Priority = rupee amount × max(age, 1) × risk weight. Showing at most 50 items per page."
    )
    display = [
        {
            "Exception": r["EXCEPTION_ID"],
            "Category": r["CATEGORY"].replace("_", " ").title(),
            "Loan": r["LOAN_ID"],
            "Channel": r["CHANNEL"],
            "Amount": rupees(r["AMOUNT_PAISE"]),
            "Age (business days)": r["AGE_BUSINESS_DAYS"],
            "Priority": round(r["PRIORITY_SCORE"]),
        }
        for r in rows
    ]
    st.dataframe(display, width="stretch", hide_index=True)
    if rows:
        chosen = st.selectbox("Select an exception", [r["EXCEPTION_ID"] for r in rows])
        st.session_state["exception_id"] = chosen
        st.caption("Open Exception detail in the sidebar to inspect the selected item.")


def exception_detail():
    st.caption("REVIEW / EVIDENCE & DECISION")
    st.title("Understand the difference")
    identifier = st.text_input("Exception ID", value=st.session_state.get("exception_id", ""))
    if not identifier:
        st.info("Select an item from the exceptions queue first.")
        return
    row = analytics.detail(identifier)
    if not row:
        st.warning("No current exception has this ID.")
        return
    st.subheader(row["CATEGORY"].replace("_", " ").title())
    columns = st.columns(3)
    columns[0].metric("Amount", rupees(row["AMOUNT_PAISE"]))
    columns[1].metric("Business-day age", row["AGE_BUSINESS_DAYS"])
    columns[2].metric("Risk weight", row["RISK_WEIGHT"])
    st.info(row["EXPLANATION"] or row["SUGGESTED_ACTION"])
    evidence = json.loads(row["EVIDENCE"])
    records = analytics.evidence_records(evidence)
    columns = st.columns(4)
    for column, label in zip(columns, ["Ledger", "Bank", "Gateway", "NACH"], strict=True):
        column.markdown(f"**{label}**")
        if records.get(label):
            for record in records[label]:
                for key, value in record.items():
                    column.markdown(
                        f"{key.replace('_', ' ').title()}: **{rupees(value) if key.endswith('PAISE') else value}**"
                    )
        else:
            column.caption("No linked record")
    st.divider()
    st.subheader("Record your decision")
    st.caption(
        "Decisions record the analyst's review in Exasol. Posting or reversing receipts remains an authorised accounting action outside this demonstration."
    )
    analyst = st.text_input("Analyst", value="Hemanth Chilakala")
    assignee = st.text_input("Assign to", placeholder="Collections owner")
    note = st.text_area("Decision note")
    buttons = st.columns(3)
    for column, label, action in zip(
        buttons,
        ["Accept recommendation", "Reject", "Assign"],
        ["ACCEPT", "REJECT", "ASSIGN"],
        strict=True,
    ):
        if column.button(label, width="stretch"):
            if action == "ASSIGN" and not assignee.strip():
                st.warning("Enter an assignee before assigning.")
            else:
                analytics.decision(identifier, action, analyst, assignee, note)
                st.success("Decision saved to the Exasol audit trail.")
    audit = query(
        "SELECT decision_action,analyst,assignee,note,created_at FROM MILAAN_AUDIT.DECISION WHERE exception_id={id!s} AND run_id={run!s} ORDER BY created_at DESC LIMIT 10",
        {"id": identifier, "run": row["RUN_ID"]},
    )
    if audit:
        st.dataframe(audit, width="stretch", hide_index=True)
    with st.expander("Structured evidence"):
        st.json(evidence)


def accuracy(data):
    st.caption("VALIDATION / KNOWN ANSWERS")
    st.title("Accuracy you can inspect")
    st.caption(
        "Measured on synthetic data with known answers. Ground truth is used only for scoring, never for matching."
    )
    scores = query("SELECT * FROM MILAAN_RES.SCORE ORDER BY break_type")
    overall = next((r for r in scores if r["BREAK_TYPE"] == "OVERALL"), None)
    if not overall:
        st.info("Run reconciliation to measure accuracy.")
        return
    columns = st.columns(3)
    columns[0].metric("Precision", f"{100 * overall['PRECISION_VALUE']:.3f}%")
    columns[1].metric("Recall", f"{100 * overall['RECALL_VALUE']:.3f}%")
    columns[2].metric("False matches", overall["FALSE_POSITIVE"])
    st.dataframe(
        [
            {
                "Break type": r["BREAK_TYPE"],
                "Correct links": r["TRUE_POSITIVE"],
                "False links": r["FALSE_POSITIVE"],
                "Missed links": r["FALSE_NEGATIVE"],
                "Precision": f"{100 * r['PRECISION_VALUE']:.3f}%"
                if r["PRECISION_VALUE"] is not None
                else "No predictions",
                "Recall": f"{100 * r['RECALL_VALUE']:.3f}%"
                if r["RECALL_VALUE"] is not None
                else "No expected matches",
            }
            for r in scores
        ],
        hide_index=True,
        width="stretch",
    )
    st.subheader("Database performance")
    rows = query(
        "SELECT pass_name,seconds,links_added,profile_json FROM MILAAN_AUDIT.PASS_TIMING WHERE run_id={run!s}",
        {"run": overall["RUN_ID"]},
    )
    st.dataframe(
        [{k: v for k, v in r.items() if k != "PROFILE_JSON"} for r in rows],
        hide_index=True,
        width="stretch",
    )
    with st.expander("Exasol's execution profiling"):
        for row in rows:
            st.markdown(f"**{row['PASS_NAME']}**")
            st.dataframe(json.loads(row["PROFILE_JSON"] or "[]"), hide_index=True, width="stretch")
    st.caption(
        "Every source record is checked for membership in at most one match group. Batch and split relationships share one group."
    )


def how():
    st.caption("DESIGN / EXASOL PERSONAL")
    st.title("Four files. One accountable close.")
    st.markdown("""**Synthetic source files** → **Exasol bulk IMPORT** → **SQL normalisation** → **seven matching passes** → **ranked exceptions** → **analyst decisions & audit**

The database performs joins, grouping, business-day checks, window functions, similarity scoring and bounded split-payment matching. Python orchestrates the passes and the dashboard reads small result sets.

1. **Exact:** reference, amount and date agree uniquely.
2. **Gateway batch:** the net batch total agrees with one bank credit.
3. **Fee aware:** gross less fees and GST agrees with the bank.
4. **Tolerant:** loan, reference suffix and amount agree within three business days.
5. **Fuzzy:** tightly blocked candidates pass name and reference similarity checks.
6. **Split / merge:** one unique subset of two or three credits equals the receipt.
7. **Classify:** unresolved items receive a category, risk weight and evidence.

Explanations are deterministic templates executed as Exasol Python UDFs. No API key is needed.

All data is synthetic, generated by `generator/`. No real customer, bank or employer data is used.""")
