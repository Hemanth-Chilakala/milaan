# Demo video: narration script

Final cut: [watch online](https://drive.google.com/file/d/1kGAxMMSWJb37wQ_lMM5eHd7PreDVZaOq/view?usp=sharing) or [demo.mp4](demo.mp4), 1920x1080, 30 fps, 2:10. Captions are burned in, so the video can be followed without sound.

All figures quoted come from measured runs on synthetic data. The month and daily timings are the unrecorded benchmark results in [benchmarks.md](../benchmarks.md). The dashboard footage is a separate recorded run, sped up in the edit and labelled on screen.

| Time | Scene | Visual | Narration |
|---|---|---|---|
| 0:00-0:08 | Hook | Kinetic type: clock at 9:00, four source files | "Nine A.M. Four files. Lakhs of payments. One analyst. And the books won't close." |
| 0:08-0:34 | Problem | Payment channels; one bank credit split into 37 gateway payments net of fees and GST; spreadsheet | "At an Indian NBFC, every EMI arrives a different way. UPI. NACH auto-debit. Payment gateways. The bank says one thing, the gateway another, the ledger a third. One bank credit can hide thirty-seven payments, after fees, after GST. So the analyst does what everyone does. Excel. Line by line. Until the evening." |
| 0:34-0:39 | Reveal | Milaan logo, "मिलान · matching" | "Meet Milaan. In Hindi, it means matching." |
| 0:39-1:03 | Month run | Dashboard: 10M source records, seven passes completing, matched share rising; 88 s and 98.5% overlay | "Here's a full month of collections. Ten million records, across four files. One click. Seven matching passes run inside Exasol: exact references, gateway batches, fees and GST, timing windows, name similarity, split payments. Eighty-eight seconds later, ninety-eight and a half percent of records are matched." |
| 1:03-1:09 | Today's close | Daily close run; 39.5 s overlay | "And today's close? Under forty seconds." |
| 1:09-1:39 | Exception | Priority queue; the ₹9,92,874.20 batch credit with its fee and GST arithmetic; plain-English explanation; Accept written to the audit trail | "What's left is a short queue, ranked by rupees at risk. Take this one: a bank credit of nearly ten lakh rupees. Milaan has unpacked it into thirty-seven gateway payments, worked out the fees and the GST, and found the one receipt that never reached the ledger. It explains why, in plain English, and recommends the fix. The analyst approves, and the decision is written to an audit trail, inside Exasol." |
| 1:39-1:56 | Proof | Accuracy page; 0 false matches across 43.8 lakh links; blind and hard validation | "Is it right? We tested it against known answers. Zero false matches, across forty-three lakh links. Even on difficult data it was never tuned for: still zero. When Milaan isn't sure, it asks a human instead of guessing." |
| 1:56-2:04 | Why Exasol | SQL snippets from the matching passes; architecture | "No data leaves the database. Matching, scoring and explanations all run inside Exasol." |
| 2:04-2:10 | Close | Logo, tagline, repository URL | "Milaan. Close the books before noon." |

## Figures used

| Claim | Measured value | Source |
|---|---|---|
| Month close, 10M source records | 88.229 s, 98.538% of records grouped | [benchmarks.md](../benchmarks.md) |
| Today's close (first arrival, 14 Oct) | 39.459 s total | [daily.md](../daily.md) |
| False links, month run | 0 across 4,384,979 links (100% precision and recall) | [benchmark_results.json](../benchmark_results.json) |
| Blind hard data (seed 20261105) | 100% precision, 85.867% recall, 0 false links | [reversals.md](../reversals.md) |
| Showcase batch credit | ₹9,92,874.20; 37 gateway payments; fees ₹8,018.71; GST ₹1,443.38 | Dashboard exception detail |
