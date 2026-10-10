# Synthetic data and matching model

`--rows N` means exactly N records across ledger, bank, gateway and NACH-return
files. Ground truth and the business calendar are separate and excluded from
that count. Break probabilities apply to payment events; multi-record events
produce different source-record percentages. Both counts are recorded in the
dataset manifest. Default event probabilities total 5%.

The generator uses a counter-based random function and seeded Faker `en_IN`
names. Changing chunk size does not change any source file. Dates are IST
business dates with a fictional holiday calendar. Fee and GST rounding use
integer paise and round half up. All bank, customer, gateway and employer
records are fictional; rates are illustrative, not industry estimates.

For datasets of at least 100 records, the first event contains 37 gateway
payments and one bank credit, with one receipt missing from the ledger. The
manifest identifies this fixed showcase separately from ordinary random events.

Source records have globally unique keys within their source. A match group can
have multiple ledger receipts and gateway payments against one batch bank
credit, or one ledger receipt against multiple split bank credits. Group
membership, rather than an individual ledger-bank edge, enforces that no source
record is consumed by two matches. Ground-truth edges record the correct
ledger-bank-gateway relationships; expected exception labels are retained for
separate classification tests. Matching rules never read the truth table.

Normalisation materialises reference suffixes and aligns the types of reference,
loan, name and paise join keys. `OPEN_LEDGER`, `OPEN_BANK` and `OPEN_PG` contain
the narrow payloads needed by matching and classification. They start complete
after loading and shrink as passes consume records. `PASS_LINK` holds only the
current pass's ledger, bank and gateway keys. A full-month rerun restores removed
rows from the immutable normalised source tables before matching. Typed truth
keys and derived scoring tables are isolated from the matching passes.

The generator refuses to overwrite existing datasets. Choose a new output
directory to regenerate. Files and manifests live under ignored `data/`.
