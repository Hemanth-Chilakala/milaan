# Bank reversal validation

Reversal checks run inside Exasol before matching. All positive credits paired with an equal debit on the same normalised reference and an equal/later date are held out, together with their debit lines. Ambiguous pairs are held for review. A late debit reopens its previous daily group; the reversal integration test verifies this behavior. Ledger and bank review items remain distinct evidence records.

| 1M set | Precision | Recall | False links | Missed links |
|---|---:|---:|---:|---:|
| Hard before handling, seed 20261104 | 99.154% | 85.872% | 3,220 | 62,123 |
| Normal | 100.000% | 100.000% | 0 | 0 |
| Blind | 100.000% | 100.000% | 0 | 0 |
| Hard (tuned) | 100.000% | 85.872% | 0 | 62,123 |
| Hard (blind) | 100.000% | 85.867% | 0 | 62,132 |

Seed 20261104 informed the change and is explicitly tuned. Seed 20261105 had never been generated before these frozen-rule runs and is explicitly blind. The brief suggested 20261104 as an unseen seed, but it had already been measured. All extra measurement CSV folders and isolated schemas were removed; the retained 10M demo dataset was unchanged. Full hashes, exact values, manifests and run IDs: [validation_results.json](validation_results.json).

All 10 prior integration tests passed in 274.70s. The additional late-reversal test passed in 23.26s against the final Lua runtime and explanation template, with self-contained schema setup. Unit tests: 34 passed. The same test verifies that resetting an unclosed date is rejected before arrivals can be prepared twice. No conflict groups or cancelled credit links remained in the new test.

The hard runs took 126.524s tuned and 130.386s blind. Classification took 64.639s and 65.856s respectively. These are measured costs; this change prioritises correct exclusion over a hard-mode runtime target. Hard recall remains limited by ambiguous references, long delays and four/five-way splits. Controlled synthetic results do not establish production accuracy.
