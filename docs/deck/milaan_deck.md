---
marp: true
theme: milaan
paginate: true
size: 16:9
footer: 'Milaan · The Singleton · ExaThon India 2026'
---

<img class='logo' src='../brand/logo.svg'>

# Closing the books<br>before noon

<div class='lead'>Payment reconciliation for the analyst who has four files and one close to finish.</div>

The Singleton · Hemanth Chilakala

ExaThon India 2026 · Track 1

---

# Meet the analyst

> A reconciliation analyst at a mid-sized Indian NBFC can't close the day's books on time because UPI, NACH and payment-gateway settlement files arrive in different formats with mismatched references, so they chase breaks by hand in Excel. If this worked, they'd close the books before noon and spend their time only on the exceptions that actually matter.

Milaan reconciles synthetic receipts for the fictional Sahyog Finance Ltd,
using Exasol Personal for normalisation, matching, scoring and audit records.

---

# One credit. 37 payments.

<div class='equation'><b>37 PayFast payments</b><span>Gross ₹10,02,336.29</span><span>− fees ₹8,018.71 − GST ₹1,443.38</span><strong>Bank credit ₹9,92,874.20</strong></div>

**36 ledger receipts present · 1 missing**

Loan SFL-BL-3979018 · missing receipt ₹31,698.77

---

# Why spreadsheets fail

<div class='cards'><div><b>References disagree</b><p>Truncated bank narrations and different receipt identifiers.</p></div><div><b>Amounts disagree</b><p>Gross EMIs, net settlements, fees and GST.</p></div><div><b>Dates disagree</b><p>Delayed credits, holidays and next-day NACH returns.</p></div></div>

Illustrative consequences: suspense balances, wrong customer follow-ups and slower audit review.

---

# Milaan in one picture

<div class='flow'><b>Ledger · Bank · Gateway · NACH</b><br>↓ bulk IMPORT<br><strong>EXASOL PERSONAL</strong><br>SQL normalisation → seven passes + UDFs → ranked exceptions<br>↓ small result sets<br><b>Analyst review → decision audit in Exasol</b></div>

Separate ground truth → SQL scoring

---

# Watch the close progress

<img class='hero' src='../screenshots/home.png'>

14 Oct 2026 · 29.49s core · 9.97s scoring · 39.46s total

Full month for scale · Today's close for arriving records and carried open items

---

# Seven passes. One shrinking queue.

<div class='pass'><span>EXACT</span><i style='width:100.00%'></i><b>3,166,424</b><small>3,166,424 cumulative</small></div>
<div class='pass'><span>PG_BATCH</span><i style='width:2.00%'></i><b>35,303</b><small>3,201,727 cumulative</small></div>
<div class='pass'><span>FEE_AWARE</span><i style='width:34.09%'></i><b>1,079,439</b><small>4,281,166 cumulative</small></div>
<div class='pass'><span>TOLERANT</span><i style='width:2.00%'></i><b>43,689</b><small>4,324,855 cumulative</small></div>
<div class='pass'><span>FUZZY</span><i style='width:2.00%'></i><b>16,024</b><small>4,340,879 cumulative</small></div>
<div class='pass'><span>SPLIT_MERGE</span><i style='width:2.00%'></i><b>44,100</b><small>4,384,979 cumulative</small></div>
<div class='pass'><span>CLASSIFY</span><i style='width:2.00%'></i><b>0</b><small>4,384,979 cumulative</small></div>

<div class='caption'>Measured 10M run · counts are receipt links · CLASSIFY labels remaining exceptions</div>

---

# Why Exasol

<div class='big'>88.23<span> seconds</span></div>

**10,000,000 source records · 4 cores · 15.62 GiB RAM**

Bulk IMPORT · hash joins · REGEXP · windows · Python scalar · Lua SET UDFs

<div class='caption'>EXACT: 22.15s · PG_BATCH: 7.63s · FEE_AWARE: 9.15s · TOLERANT: 1.79s · FUZZY: 0.91s · SPLIT_MERGE: 3.11s · CLASSIFY: 9.88s</div>

Database-side results, validation and scoring included. Explanations and profiling flush follow the timer.

---

# Review the money that matters

<div class='screens'><img src='../screenshots/queue.png'><img src='../screenshots/detail.png'></div>

**Prioritise → inspect evidence → accept, reject or assign**

Every review records the analyst, timestamp and reasoning in Exasol.

---

# Accuracy, tested four ways

| 1M dataset | Precision | Recall | False links |
|---|---:|---:|---:|
| Normal | 100.000% | 100.000% | 0 |
| Blind | 100.000% | 100.000% | 0 |
| Hard (tuned) | 100.000% | 85.872% | 0 |
| Hard (blind) | 100.000% | 85.867% | 0 |

**10M normal:** 100.000% precision · 100.000% recall · 98.538% source membership

Normal and reused blind are regression checks. Hard (tuned) informed reversal handling; hard (blind) uses newly unseen seed 20261105.

---

# Trust comes from evidence

<div class='cards'><div><b>Deterministic explanations</b><p>Amounts, dates and rules come from stored evidence. No external inference service.</p></div><div><b>Human review</b><p>The analyst accepts a recommendation, rejects it or assigns an owner.</p></div><div><b>Auditable decisions</b><p>Run-linked evidence and review history remain in Exasol.</p></div></div>

A final membership check rejects conflicting match groups.

---

# A practical path to impact

**First:** independently labelled validation with an NBFC partner.

**Next:** live feeds, real holiday calendars, authenticated review roles and approved ledger write-back.

**Then:** measure larger datasets and concurrent operations.

Similar reconciliation workflows exist in banks, insurers, fintechs and gateway-based merchants.

---

<img class='logo' src='../brand/logo.svg'>

# Close with confidence

The Singleton · Hemanth Chilakala

https://github.com/Hemanth-Chilakala/milaan

Demo video: docs/video/demo.mp4

MIT · All data is synthetic

---

# Appendix: limitations & methodology

- Seeded, controlled data; production accuracy needs independent partner labels.
- Reversal pairs excluded before matching; late debits reopen prior groups.
- Split search: at most 12 candidates, subsets of two or three.
- Single node and one worker; no real ledger connector or review authentication.
- Timing includes preparation, results, validation and scoring; browser/recording load changes it.
- Fixture and three consecutive 10M closes agree with month; full 30-day 10M replay unmeasured.
- Codespace rebuild and clean checkout tested; macOS/WSL remain unverified.

Run IDs, profiles and raw observations: docs/benchmarks.md
