# Fictional identifiers and validation

Source IDs use seeded bijections over bounded namespaces. Loan IDs have a fictional
Sahyog product code and seven digits; gateway IDs have twelve mixed-case letters
and digits after `pf_`; RRNs have twelve digits; settlement UTRs begin `BUBN`;
UMRNs begin `BUB7`; bank and receipt IDs have eight digits. Normalised gateway
references remain unique after uppercasing. Exhausting a namespace raises an error
rather than silently reusing an identifier.

Batch sequences are unique within their payment date. Six digits are used because
10M records require more than 99 settlements per date. The showcase is selected
around 45–55% through the source stream, independently of generation chunk size.
It has 37 distinct loans and varied customer names and amounts, paid on
27 Oct 2026. Its identifiers are recorded in the dataset manifest, and the app
and capture tools read that manifest rather than hardcoding an exception ID.

An initial generation attempt exhausted a global one-million-batch namespace.
The per-date namespace fixes that capacity error. The first accuracy check also
found that Jaro-Winkler reference scores benefited from the previous repeated
reference digits. Normal recall fell to 99.833% and reused blind recall to 99.898%.
The suffix-blocked fuzzy pass now explicitly recognises a single edit between
12-character references while retaining its name, amount, date and uniqueness
checks. Repeated measurements below include that correction.

| 1M validation set | Previous precision | Current precision | Previous recall | Current recall | Current false / missed links |
|---|---:|---:|---:|---:|---:|
| Normal, seed 42 | 100% | 100% | 100% | 100% | 0 / 0 |
| Reused blind, seed 20261025 | 100% | 100% | 100% | 100% | 0 / 0 |
| Hard, seed 20261104 | 99.1544% | 99.1544% | 85.872% | 85.8719% | 3,220 / 62,123 |

Hard precision is unchanged and rounded recall is unchanged. Two additional
expected edges are missed compared with the previous 62,121: moving the showcase
changes the final source-budget boundary and its event mix. No reversal rules
were tuned in this task. The normal and blind seeds are reused regression sets,
not new independent validation. A new blind hard set follows reversal tuning.

The small fixture has 437 correct links, no false or missed links, and every break
type. Its stored snapshot was refreshed only after the independent ground-truth
comparison passed. Determinism, exact source budgets, identifier uniqueness,
per-date capacity, rupee totals and gateway fee equations have unit checks.
Raw observations and prior values are in [id_validation_results.json](id_validation_results.json).
