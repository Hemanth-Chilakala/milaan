---
marp: true
theme: default
paginate: true
size: 16:9
footer: 'Milaan · The Singleton · ExaThon India 2026'
style: |
  section { background: #f7fafb; color: #172b3a; font-family: 'DejaVu Sans', sans-serif; font-size: 27px; padding: 52px 64px; }
  h1 { color: #0f766e; font-size: 46px; letter-spacing: -1.2px; }
  h2 { color: #334155; font-size: 34px; }
  blockquote { border-left: 7px solid #14b8a6; padding: 12px 24px; color: #172b3a; font-size: 29px; }
  footer { color: #64748b; font-size: 14px; }
  table { font-size: 22px; }
  .big { font-size: 82px; color: #0f766e; font-weight: bold; }
  .equation { background: white; border: 2px solid #d7e7e5; border-radius: 18px; padding: 24px; display: flex; flex-direction: column; gap: 12px; }
  .equation strong { color: #0f766e; font-size: 38px; }
  .flow { text-align: center; line-height: 2.2; background: white; border-radius: 16px; padding: 22px; }
  .screens { display:flex; gap:18px; }
  .screens img { width:48%; height:300px; object-fit:contain; background:white; border:1px solid #d7e7e5; }
  .metrics { display:flex; gap:24px; padding:20px 0; }
  .metrics div { flex:1; background:white; padding:22px; border-radius:16px; }
  .metrics strong { font-size:46px; color:#0f766e; }
---

# Milaan
## Closing the books before noon

The Singleton · Hemanth Chilakala

ExaThon India 2026 · Track 1: Money, Risk & Regulation

**An accountable close, powered by Exasol Personal.**

---

# Meet the reconciliation analyst

> A reconciliation analyst at a mid-sized Indian NBFC can't close the day's books on time because UPI, NACH and payment-gateway settlement files arrive in different formats with mismatched references, so they chase breaks by hand in Excel. If this worked, they'd close the books before noon and spend their time only on the exceptions that actually matter.

Milaan reconciles synthetic receipts for the fictional Sahyog Finance Ltd,
using Exasol Personal for normalisation, matching, scoring and audit records.

The person: a finance analyst at a mid-sized Indian NBFC.
The desired outcome: investigate meaningful exceptions instead of every receipt.

---

# One credit can represent 37 payments

<div class='equation'><b>37 PayFast payments</b><span>gross ₹6,07,085.27</span><span>− fees ₹4,856.70 − GST ₹874.21</span><strong>One bank credit: ₹6,01,354.36</strong></div>

Four channels · different formats · T+1/T+2 timing · truncated references · NACH returns

Measured synthetic showcase; 36 receipts are present and one is missing.

---

# The cost of an unresolved close

**Money in suspense** delays explanation of the cash balance.

**Misstated customer dues** can prompt a call to someone who already paid.

**Unclear evidence** adds effort to accounting review and audit.

Illustrative workflow consequences. No industry cost or productivity statistic is claimed.

---

# Everything heavy runs inside Exasol

<div class='flow'><b>Four source CSVs</b> → <b>Bulk IMPORT</b> → <b>SQL normalisation</b><br>↓<br><b>7 matching passes + UDFs</b> → <b>Ranked exceptions</b><br>↓<br><b>Streamlit analyst review</b> → <b>Exasol decision audit</b></div>

Ground truth enters only the SQL scoring path. Python orchestrates; the database reconciles.

---

# Seven passes, measured at 10M

| Pass | Receipt links | Time |
|---|---:|---:|
| EXACT | 3,164,644 | 25.34s |
| PG_BATCH | 35,303 | 18.67s |
| FEE_AWARE | 1,079,439 | 17.20s |
| TOLERANT | 43,689 | 6.47s |
| FUZZY | 16,025 | 4.78s |
| SPLIT_MERGE | 44,100 | 31.60s |
| CLASSIFY | 0 | 39.61s |

Passes use remaining keys only. One-to-many and many-to-one relationships share a single group ID.

---

# Why Exasol Personal

<div class='big'>203.88 seconds</div>

**10,000,000 source records** across four files.

SQL joins, aggregation and windows · bulk IMPORT · Python scalar and SET UDFs

Measured on 4 cores / 15.62 GiB RAM.
Timing includes results, conflict validation and SQL scoring; explanations and profiling flush are separate. Live-recorded run when available; timings vary between runs.

---

# Review the money that needs attention

<div class='screens'><img src='../screenshots/queue.png'><img src='../screenshots/detail.png'></div>

Rank by amount × business-day age × risk. Inspect source evidence. Accept a recommendation, reject it or assign an owner.

---

# Accuracy against known answers

<div class='metrics'><div><strong>100.000%</strong><br>precision</div><div><strong>99.959%</strong><br>recall</div><div><strong>98.502%</strong><br>source records grouped</div></div>

0 false links · 1,779 missed expected links · 103,564 exceptions

Conflict validation rejects records assigned to multiple groups. These seeded results do not establish real-world accuracy; corruption patterns and distinct loans are deliberately constrained.

---

# Trust comes from evidence

**Deterministic explanations:** amounts, dates and rules come from stored evidence.

**Human review:** decisions are recorded, not silently posted to a real ledger.

**Run-linked audit:** analyst, timestamp, assignment and note stay in Exasol.

No external inference API. PII masking is tested for a future optional rewrite; that integration is not shipped.

---

# A practical path to operational impact

**First:** validate with an NBFC partner using independently labelled, anonymised cases.

**Next:** live SFTP/API feeds, real business calendars, review roles and approved ledger write-back.

**Then:** measure larger datasets and distributed coordination.

The same pattern may help banks, insurers, fintechs and gateway-based merchants. Applicability is a hypothesis to test.

---

# Close the books with confidence

**Milaan · The Singleton · Hemanth Chilakala**

Repository destination:
https://github.com/Hemanth-Chilakala/milaan

Demo: `docs/video/demo.mp4`

MIT · synthetic data only · Exasol Personal

Thank you.
