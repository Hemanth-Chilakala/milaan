"""Generate source records in bounded chunks; no real customer or bank data is used."""

import argparse
import csv
import hashlib
import json
from collections import Counter
from contextlib import ExitStack
from datetime import date, timedelta
from pathlib import Path
from time import perf_counter

import numpy as np
import yaml
from faker import Faker

HEADERS = {
    "ledger": "ledger_id loan_id customer_name emi_due_date amount_paise channel external_ref posted_date status".split(),
    "bank_statement": "bank_txn_id value_date narration credit_paise debit_paise bank_ref".split(),
    "pg_settlement": "pg_payment_id order_ref gross_paise fee_paise gst_on_fee_paise net_paise payment_date settlement_batch_id settlement_date settlement_utr".split(),
    "nach_returns": "umrn loan_id amount_paise presentation_date return_date return_reason".split(),
    "ground_truth": "event_id ledger_id bank_txn_id pg_payment_id break_type expected_match expected_category ledger_paise bank_paise fee_paise gst_paise refund_paise".split(),
    "calendar": "calendar_date business_day_index is_business_day".split(),
}
DEFAULT_CONFIG = Path(__file__).with_name("config.yaml")


def load_config(path: Path = DEFAULT_CONFIG) -> dict:
    config = yaml.safe_load(path.read_text())
    rates = config["break_rates"]
    if any(not 0 <= float(rate) <= 1 for rate in rates.values()) or sum(rates.values()) > 1:
        raise ValueError("Break rates must be nonnegative and total at most one.")
    if not 2 <= config["batch_size"] <= 37:
        raise ValueError("Batch size must be between 2 and 37.")
    return config


def business_dates(start: date, days: int, holidays: set[date]) -> list[date]:
    return [
        d
        for offset in range(days)
        if (d := start + timedelta(days=offset)).weekday() < 5 and d not in holidays
    ]


def add_business_days(day: date, count: int, holidays: set[date]) -> date:
    while count:
        day += timedelta(days=1)
        if day.weekday() < 5 and day not in holidays:
            count -= 1
    return day


def random_words(ids: np.ndarray, seed: int, salt: int) -> np.ndarray:
    """Counter-based SplitMix64: output does not depend on chunk boundaries."""
    with np.errstate(over="ignore"):
        words = ids.astype(np.uint64) + np.uint64((seed + salt) % (2**64))
        words = words + np.uint64(0x9E3779B97F4A7C15)
        words = (words ^ (words >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        words = (words ^ (words >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        return words ^ (words >> np.uint64(31))


def generate(
    out: Path,
    rows: int,
    seed: int = 42,
    days: int = 30,
    chunk_size: int = 20_000,
    config_path: Path = DEFAULT_CONFIG,
    fixture: bool = False,
) -> dict:
    if rows < 1 or days < 1 or chunk_size < 1:
        raise ValueError("rows, days and chunk_size must be positive.")
    if out.exists() and any((out / f"{name}.csv").exists() for name in HEADERS):
        raise FileExistsError("Output already contains a dataset; choose a fresh --out directory.")
    config = load_config(config_path)
    holidays = {date.fromisoformat(value) for value in config["fictional_holidays"]}
    start = date(2026, 10, 1)
    dates = business_dates(start, days, holidays)
    if not dates:
        raise ValueError("Date range contains no business days.")
    faker = Faker("en_IN")
    faker.seed_instance(seed)
    names = [faker.name().replace("/", " ").replace("|", " ") for _ in range(2048)]
    out.mkdir(parents=True, exist_ok=True)
    counts: Counter = Counter()
    event_counts: Counter = Counter()
    sums: Counter = Counter()
    cumulative = np.cumsum(list(config["break_rates"].values()))
    types = list(config["break_rates"]) + ["CLEAN"]
    started = perf_counter()
    source_count = 0
    event_id = 0

    with ExitStack() as stack:
        writers = {}
        for name, header in HEADERS.items():
            handle = stack.enter_context(
                (out / f"{name}.csv").open("w", newline="", encoding="utf-8")
            )
            writers[name] = csv.writer(handle, lineterminator="\n")
            writers[name].writerow(header)

        def emit(table: str, record: list) -> None:
            nonlocal source_count
            writers[table].writerow(record)
            counts[table] += 1
            if table not in ("ground_truth", "calendar"):
                source_count += 1
            if table == "ledger":
                sums["ledger_paise"] += record[4]
            elif table == "bank_statement":
                sums["bank_paise"] += record[3] - record[4]
            elif table == "pg_settlement":
                for key, index in (
                    ("gateway_gross_paise", 2),
                    ("fee_paise", 3),
                    ("gst_paise", 4),
                    ("gateway_net_paise", 5),
                ):
                    sums[key] += record[index]

        def event(
            i: int, kind: str, amount: int, day: date, name: str, channel: str, batch_size: int = 0
        ) -> tuple[dict, list]:
            records = {key: [] for key in HEADERS if key not in ("calendar", "ground_truth")}
            truths = []
            loan, ledger, bank, ref = (
                f"LN-{100000 + i}",
                f"L{i:09d}",
                f"B{i:09d}",
                str(410000000000 + i),
            )
            if kind == "NACH_BOUNCE_MISPOSTED":
                channel = "NACH"
            if kind in ("FEE_NETTING", "BATCH_SETTLEMENT", "REFUND_REVERSAL"):
                channel = "PG"
            if kind in (
                "SPLIT_PAYMENT",
                "NAME_MISMATCH",
                "REF_TRUNCATED",
                "PARTIAL_PAYMENT",
                "UNIDENTIFIED_CREDIT",
            ):
                channel = "UPI"
            if channel == "NACH":
                ref = f"BUB{7000000000 + i}"
            pg_id = f"PG{i:09d}" if channel == "PG" else ""
            if pg_id:
                ref = pg_id
            credit_day = add_business_days(day, 2, holidays) if kind == "TIMING" else day
            expected = kind not in (
                "PARTIAL_PAYMENT",
                "NACH_BOUNCE_MISPOSTED",
                "UNIDENTIFIED_CREDIT",
                "MISSING_IN_BANK",
            )

            def truth(
                ledger_key: str,
                b: str,
                p: str,
                matched: bool,
                cat: str,
                lp: int,
                bp: int,
                fee: int = 0,
                gst: int = 0,
                refund: int = 0,
            ) -> None:
                truths.append(
                    [
                        f"E{i:09d}",
                        ledger_key,
                        b,
                        p,
                        kind,
                        int(matched),
                        cat,
                        lp,
                        bp,
                        fee,
                        gst,
                        refund,
                    ]
                )

            if kind == "BATCH_SETTLEMENT":
                size = batch_size or config["batch_size"]
                batch = f"B-{day:%Y%m%d}-{i:09d}"
                utr = f"SAHY{i:012d}"
                settle = add_business_days(day, 2, holidays)
                total = 0
                for j in range(size):
                    value = amount + j * 100
                    fee = (value * config["fee_basis_points"] + 5000) // 10000
                    gst = (fee * 18 + 50) // 100
                    net = value - fee - gst
                    lid, pid, loan_j = f"{ledger}-{j:02d}", f"{pg_id}-{j:02d}", f"{loan}-{j:02d}"
                    missing = batch_size == 37 and j == 36
                    if not missing:
                        records["ledger"].append(
                            [
                                lid,
                                loan_j,
                                names[(i + j) % len(names)],
                                day,
                                value,
                                "PG",
                                pid,
                                day,
                                "PAID",
                            ]
                        )
                    records["pg_settlement"].append(
                        [pid, loan_j, value, fee, gst, net, day, batch, settle, utr]
                    )
                    total += net
                    truth(
                        "" if missing else lid,
                        bank,
                        pid,
                        not missing,
                        "MISSING_IN_LEDGER" if missing else "",
                        value if not missing else 0,
                        net,
                        fee,
                        gst,
                    )
                records["bank_statement"].append(
                    [bank, settle, f"NEFT-{utr}-PAYFAST SETTLEMENT {batch}", total, 0, utr]
                )
                return records, truths

            if kind != "UNIDENTIFIED_CREDIT":
                records["ledger"].append(
                    [ledger, loan, name, day, amount, channel, ref, day, "PAID"]
                )
            if kind == "DUPLICATE_POSTING":
                records["ledger"].append(
                    [ledger + "-D", loan, name, day, amount, channel, ref, day, "PAID"]
                )
            if kind == "NACH_BOUNCE_MISPOSTED":
                records["nach_returns"].append(
                    [
                        ref,
                        loan,
                        amount,
                        day,
                        add_business_days(day, 1, holidays),
                        ("INSUFFICIENT_FUNDS", "ACCOUNT_CLOSED", "MANDATE_CANCELLED")[i % 3],
                    ]
                )
                truth(ledger, "", "", False, kind, amount, 0)
                return records, truths
            if kind == "MISSING_IN_BANK":
                truth(ledger, "", "", False, kind, amount, 0)
                return records, truths
            if kind == "SPLIT_PAYMENT":
                n = 2 + i % 2
                parts = [amount // n] * (n - 1)
                parts.append(amount - sum(parts))
                for j, value in enumerate(parts):
                    bid, sub_ref = f"{bank}-{j}", f"{ref}S{j}"
                    records["bank_statement"].append(
                        [bid, day, f"UPI/CR/{sub_ref}/{name}/bub/EMI {loan}", value, 0, sub_ref]
                    )
                    truth(ledger, bid, "", True, "", amount if j == 0 else 0, value)
                return records, truths

            fee = gst = refund = 0
            credit = amount
            if channel == "PG":
                fee = (amount * config["fee_basis_points"] + 5000) // 10000
                gst = (fee * 18 + 50) // 100
                batch = f"B-{day:%Y%m%d}-{i:09d}"
                credit_day = add_business_days(day, 1 + i % 2, holidays)
                # Unbatched settlements carry the payment reference directly.
                bank_ref = pg_id
                credit = amount - fee - gst
                records["pg_settlement"].append(
                    [pg_id, loan, amount, fee, gst, credit, day, batch, credit_day, bank_ref]
                )
                if kind == "REFUND_REVERSAL":
                    refund = amount // 5
                    records["pg_settlement"].append(
                        [
                            pg_id + "-RF",
                            "REFUND:" + pg_id,
                            -refund,
                            0,
                            0,
                            -refund,
                            day,
                            batch,
                            credit_day,
                            bank_ref,
                        ]
                    )
                    credit -= refund
                    narration = f"NEFT-{bank_ref}-PAYFAST SETTLEMENT {batch}"
                else:
                    narration = f"PAYFAST/{pg_id}/{name}/EMI {loan}"
            else:
                bank_ref = ref
                shown_name = name
                shown_loan = loan
                if kind == "PARTIAL_PAYMENT":
                    credit = amount * 65 // 100
                if kind == "REF_TRUNCATED":
                    bank_ref = ref[-8:]
                if kind == "NAME_MISMATCH":
                    shown_name = name[:-1]
                    shown_loan = ""
                    bank_ref = "9" + ref[1:]
                if channel == "NACH":
                    narration = f"NACH CR UMRN {ref} EMI {loan}"
                elif channel == "NEFT":
                    narration = f"NEFT/{bank_ref}/{shown_name}/EMI {shown_loan}"
                else:
                    narration = f"UPI/CR/{bank_ref}/{shown_name}/bub/EMI {shown_loan}"
            records["bank_statement"].append([bank, credit_day, narration, credit, 0, bank_ref])
            truth(
                "" if kind == "UNIDENTIFIED_CREDIT" else ledger,
                bank,
                pg_id,
                expected,
                "" if expected else kind,
                0 if kind == "UNIDENTIFIED_CREDIT" else amount,
                credit,
                fee,
                gst,
                refund,
            )
            if kind == "DUPLICATE_POSTING":
                truth(ledger + "-D", "", "", False, kind, amount, 0)
            return records, truths

        # A reproducible analyst example: 37 gateway payments, 36 ledger receipts.
        showcase = rows >= 100
        forced = ["BATCH_SETTLEMENT"] + list(config["break_rates"]) if fixture else []
        while source_count < rows:
            ids = np.arange(event_id, event_id + chunk_size, dtype=np.uint64)
            category_values = random_words(ids, seed, 0) / float(2**64)
            categories = np.searchsorted(cumulative, category_values)
            amounts = random_words(ids, seed, 1009) % np.uint64(3_100_001) + np.uint64(400_000)
            day_ids = random_words(ids, seed, 2017) % np.uint64(len(dates))
            name_ids = random_words(ids, seed, 3011) % np.uint64(len(names))
            channels = random_words(ids, seed, 4001) % np.uint64(4)
            for offset, raw_id in enumerate(ids):
                i = int(raw_id)
                kind = types[int(categories[offset])]
                special_size = 37 if showcase and i == 0 else 0
                if special_size:
                    kind = "BATCH_SETTLEMENT"
                elif fixture and i < len(forced):
                    kind = forced[i]
                records, truths = event(
                    i,
                    kind,
                    int(amounts[offset]),
                    dates[int(day_ids[offset])],
                    names[int(name_ids[offset])],
                    ("UPI", "NACH", "PG", "NEFT")[int(channels[offset])],
                    special_size,
                )
                required = sum(map(len, records.values()))
                remaining = rows - source_count
                if required > remaining:
                    if remaining >= 2:
                        kind = "CLEAN"
                        records, truths = event(
                            i,
                            kind,
                            int(amounts[offset]),
                            dates[int(day_ids[offset])],
                            names[int(name_ids[offset])],
                            "UPI",
                        )
                    else:
                        kind = "UNIDENTIFIED_CREDIT"
                        records, truths = event(
                            i,
                            kind,
                            int(amounts[offset]),
                            dates[int(day_ids[offset])],
                            names[int(name_ids[offset])],
                            "UPI",
                        )
                for table, values in records.items():
                    for value in values:
                        emit(table, value)
                for truth_record in truths:
                    emit("ground_truth", truth_record)
                event_counts[kind] += 1
                event_id += 1
                if source_count == rows:
                    break
        business_index = 0
        # Includes settlement grace days and an explicit as-of business date.
        for offset in range(-10, days + 15):
            day = start + timedelta(days=offset)
            is_business = day.weekday() < 5 and day not in holidays
            business_index += int(is_business)
            emit("calendar", [day, business_index, int(is_business)])

    manifest = {
        "seed": seed,
        "requested_source_rows": rows,
        "source_rows": source_count,
        "payment_events": event_id,
        "days": days,
        "start_date": str(start),
        "as_of_date": str(add_business_days(start + timedelta(days=days + 7), 1, holidays)),
        "source_counts": dict(counts),
        "event_counts": dict(event_counts),
        "totals": dict(sums),
        "rates": config["break_rates"],
        "showcase": showcase,
        "fixture": fixture,
        "sha256": {
            name: hashlib.file_digest((out / f"{name}.csv").open("rb"), "sha256").hexdigest()
            for name in HEADERS
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        json.dumps(
            {
                "source_rows": source_count,
                "events": event_id,
                "seconds": round(perf_counter() - started, 3),
            },
            indent=2,
        )
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--rows", type=int, default=1_000_000)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--chunk-size", type=int, default=20_000)
    parser.add_argument("--out", type=Path, default=Path("data/1m"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--fixture", action="store_true")
    args = parser.parse_args()
    generate(args.out, args.rows, args.seed, args.days, args.chunk_size, args.config, args.fixture)


if __name__ == "__main__":
    main()
