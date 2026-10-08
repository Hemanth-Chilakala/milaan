# Demo narration

Milaan means matching. Meet a reconciliation analyst at a mid-sized Indian non-banking finance company. Each morning, the ledger says which loan instalments were paid. The bank, gateway and auto-debit return files tell different parts of the story. The analyst has to explain the differences before closing the books.

A spreadsheet join is not enough. One bank credit can cover thirty-seven gateway payments, after fees and tax. References can be shortened, settlement can arrive later, and a returned auto-debit can still look paid in the ledger. Milaan brings these records into one evidence-based workflow.

Here are ten million source records across four files. Reconciliation runs inside Exasol Personal. The timer shows the real elapsed time as each pass completes. Exact reference matching comes first, followed by gateway batches, fee-aware matching, business-day tolerance, name similarity and bounded split payments. The recorded run took 114.49 seconds, including result validation and SQL accuracy scoring. 98.50 percent of source records belong to matched groups. Every record is checked for conflicting group membership. The dashboard retrieves small result sets rather than moving millions of records into Python.

The analyst now works from a queue ranked by rupee impact, business-day age and risk. Open this missing-ledger exception. The bank credit agrees with a batch of thirty-seven gateway payments, but only thirty-six ledger receipts are present. The explanation identifies the missing payment and loan, with the actual amount, fees and tax. These words are generated from stored evidence inside Exasol, without an outside service. The analyst can accept the recommendation, reject it, or assign an owner. The decision, analyst and timestamp are written back to the audit trail.

The accuracy panel compares predicted links with separate synthetic ground truth. This run measured 100.000 percent precision and 99.959 percent recall. These are seeded demonstration results, not a claim about real customer data. The panel also exposes pass timings and Exasol execution profiles.

Milaan keeps the heavy work in Exasol: bulk imports, SQL joins, window functions, matching scripts, explanations and scoring. Python manages the workflow. The next step is validation with an NBFC partner and independently labelled cases.

Milaan. The Singleton. Hemanth Chilakala. Synthetic data, an MIT licence, and an accountable daily close.
