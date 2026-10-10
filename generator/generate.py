"""Generate source records in bounded chunks; no real customer or bank data is used."""

import argparse
import csv
import hashlib
import json
import math
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
ID_SCHEME = "seeded collision-free namespace bijections v2"


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


class Identifiers:
    """Seeded bijections, bounded by namespace size, without collision sets."""

    def __init__(self, seed):
        self.seed = seed
        self.counters = Counter()
        self.parameters = {}

    def number(self, kind, modulus):
        index = self.counters[kind]
        if index >= modulus:
            raise ValueError(f"Identifier namespace exhausted: {kind}")
        self.counters[kind] += 1
        if kind not in self.parameters:
            salt = int.from_bytes(hashlib.sha256(kind.encode()).digest()[:8], "big")
            word = int(random_words(np.array([0], dtype=np.uint64), self.seed, salt)[0])
            multiplier = word % modulus
            while math.gcd(multiplier, modulus) != 1:
                multiplier += 1
            self.parameters[kind] = (multiplier, (word >> 17) % modulus)
        multiplier, offset = self.parameters[kind]
        return (index * multiplier + offset) % modulus

    def loan(self):
        value = self.number("loan", 40_000_000)
        return f"SFL-{('HL', 'PL', 'BL', 'GL')[value // 10_000_000]}-{value % 10_000_000:07d}"

    def gateway(self):
        # Case changes are cosmetic: canonical uppercase references stay unique.
        value = self.number("gateway", 36**12)
        chars = []
        for index in range(12):
            value, digit = divmod(value, 36)
            character = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"[digit]
            chars.append(character.lower() if index % 3 == 1 else character)
        return "pf_" + "".join(reversed(chars))

    def bank(self):
        return f"BUB-TXN-{self.number('bank', 100_000_000):08d}"

    def ledger(self):
        return f"SFL-RCT-{self.number('ledger', 100_000_000):08d}"

    def rrn(self):
        return f"{self.number('rrn', 10**12):012d}"

    def umrn(self):
        return f"BUB7{self.number('umrn', 10**12):012d}"

    def utr(self):
        return f"BUBN{self.number('utr', 10**11):011d}"

    def batch(self, day):
        # 10M records need more than 99 batches per date. Six digits retain uniqueness.
        return f"PF-B-{day:%Y%m%d}-{self.number('batch_' + str(day), 1_000_000):06d}"


def generate(
    out: Path,
    rows: int,
    seed: int = 42,
    days: int = 30,
    chunk_size: int = 20_000,
    config_path: Path = DEFAULT_CONFIG,
    fixture: bool = False,
    difficulty: str = "normal",
    randomise_rates: bool = False,
) -> dict:
    if rows < 1 or days < 1 or chunk_size < 1:
        raise ValueError("rows, days and chunk_size must be positive.")
    if out.exists() and any((out / f"{name}.csv").exists() for name in HEADERS):
        raise FileExistsError("Output already contains a dataset; choose a fresh --out directory.")
    config = load_config(config_path)
    if difficulty not in {"normal", "hard"}:
        raise ValueError("difficulty must be normal or hard")
    rate_multipliers = {}
    if randomise_rates:
        rng = np.random.default_rng(seed)
        for kind, rate in config["break_rates"].items():
            rate_multipliers[kind] = float(rng.uniform(0.5, 1.5))
            config["break_rates"][kind] = rate * rate_multipliers[kind]
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
    hard_counts: Counter = Counter()
    current_hard: list[str] = []
    cumulative = np.cumsum(list(config["break_rates"].values()))
    types = list(config["break_rates"]) + ["CLEAN"]
    started = perf_counter()
    source_count = 0
    event_id = 0
    identifiers = Identifiers(seed)
    showcase_info = {}
    # Selected from the middle of the source stream, independent of chunk size.
    showcase_threshold = rows * (45 + seed % 11) // 100

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
            i: int,
            kind: str,
            amount: int,
            day: date,
            name: str,
            channel: str,
            batch_size: int = 0,
            allow_hard: bool = True,
        ) -> tuple[dict, list]:
            records = {key: [] for key in HEADERS if key not in ("calendar", "ground_truth")}
            truths = []
            current_hard.clear()
            hard = difficulty == "hard" and allow_hard and batch_size != 37
            loan, ledger, bank, ref = (
                identifiers.loan(),
                identifiers.ledger(),
                identifiers.bank(),
                identifiers.rrn(),
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
                ref = identifiers.umrn()
            pg_id = identifiers.gateway() if channel == "PG" else ""
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

            # Two customers in the same loan product pay the same instalment.
            # Both banks retain only a shared reference suffix and omit the loan.
            # The event oracle knows the original links before those fields degrade.
            if hard and kind == "CLEAN" and i % 17 == 0:
                current_hard.append("AMOUNT_DAY_COLLISION")
                suffix = f"{i % 100000000:08d}"
                for j, customer in enumerate(("Rahul Kumar", "Rahul Kumari")):
                    lid, bid, loan_j = identifiers.ledger(), identifiers.bank(), identifiers.loan()
                    full_ref = f"{5100 + j}{suffix}"
                    records["ledger"].append(
                        [lid, loan_j, customer, day, 1_500_000, "UPI", full_ref, day, "PAID"]
                    )
                    records["bank_statement"].append(
                        [bid, day, f"UPI/CR/{suffix}/{customer}/bub/EMI ", 1_500_000, 0, suffix]
                    )
                    truth(lid, bid, "", True, "", 1_500_000, 1_500_000)
                return records, truths

            if hard and kind == "TIMING":
                credit_day = add_business_days(day, 4 + i % 2, holidays)
                current_hard.append("DELAY_T4_T5")

            if kind == "BATCH_SETTLEMENT":
                size = batch_size or config["batch_size"]
                batch = identifiers.batch(day)
                utr = identifiers.utr()
                settle = add_business_days(day, 2, holidays)
                total = 0
                for j in range(size):
                    value = (amount + j * 7919 + (j * j * 371)) % 3_100_001 + 400_000
                    fee = (value * config["fee_basis_points"] + 5000) // 10000
                    gst = (fee * 18 + 50) // 100
                    net = value - fee - gst
                    lid, pid, loan_j = (
                        identifiers.ledger(),
                        identifiers.gateway(),
                        identifiers.loan(),
                    )
                    missing = batch_size == 37 and j == 36
                    if missing:
                        showcase_info.update(
                            event_index=i,
                            batch_id=batch,
                            bank_txn_id=bank,
                            pg_payment_id=pid,
                            loan_id=loan_j,
                            exception_id="PG:" + pid,
                            payment_date=str(day),
                        )
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
                n = 4 + i % 2 if hard else 2 + i % 2
                if hard:
                    current_hard.append("SPLIT_4_PLUS")
                parts = [amount // n] * (n - 1)
                parts.append(amount - sum(parts))
                for j, value in enumerate(parts):
                    bid, sub_ref = identifiers.bank(), identifiers.rrn()
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
                batch = identifiers.batch(day)
                credit_day = add_business_days(day, 1 + i % 2, holidays)
                if hard and kind == "TIMING":
                    credit_day = add_business_days(day, 4 + i % 2, holidays)
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
                if hard and kind == "FEE_NETTING":
                    credit += -1 if i % 2 else 1
                    current_hard.append("FEE_ROUNDING_1_PAISE")
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
                    if hard:
                        # Two substitutions, rather than a single clipped character.
                        chars = list(name)
                        for pos in (0, max(1, len(chars) // 2)):
                            chars[pos] = "Z" if chars[pos] != "Z" else "X"
                        shown_name = "".join(chars)
                        bank_ref = ref[-6:]
                        current_hard.append("TWO_TYPOS_TRUNCATED_REF")
                if channel == "NACH":
                    narration = f"NACH CR UMRN {ref} EMI {loan}"
                elif channel == "NEFT":
                    narration = f"NEFT/{bank_ref}/{shown_name}/EMI {shown_loan}"
                else:
                    narration = f"UPI/CR/{bank_ref}/{shown_name}/bub/EMI {shown_loan}"
            records["bank_statement"].append([bank, credit_day, narration, credit, 0, bank_ref])
            reversal = hard and kind == "CLEAN" and channel == "UPI" and i % 29 == 0
            duplicate = (
                hard and kind == "CLEAN" and channel == "UPI" and i % 31 == 0 and not reversal
            )
            if reversal:
                expected = False
                current_hard.append("REVERSED_BANK_LINE")
                records["bank_statement"].append(
                    [bank + "-RV", credit_day, "REVERSAL " + narration, 0, credit, bank_ref]
                )
                truth("", bank + "-RV", "", False, "BANK_REVERSAL", 0, -credit)
            elif duplicate:
                current_hard.append("DUPLICATED_BANK_LINE")
                records["bank_statement"].append(
                    [bank + "-D", credit_day, narration, credit, 0, bank_ref]
                )
                truth("", bank + "-D", "", False, "DUPLICATE_BANK", 0, credit)
            truth(
                "" if kind == "UNIDENTIFIED_CREDIT" else ledger,
                bank,
                pg_id,
                expected,
                "BANK_REVERSAL" if reversal else ("" if expected else kind),
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
        showcase = rows >= 300
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
                special_size = (
                    37
                    if showcase
                    and not showcase_info
                    and source_count >= showcase_threshold
                    and rows - source_count >= 74
                    else 0
                )
                if special_size:
                    kind = "BATCH_SETTLEMENT"
                elif fixture and i < len(forced):
                    kind = forced[i]
                records, truths = event(
                    i,
                    kind,
                    int(amounts[offset]),
                    (
                        date(2026, 10, 27)
                        if special_size and days >= 27
                        else dates[int(day_ids[offset])]
                    ),
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
                            allow_hard=False,
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
                            allow_hard=False,
                        )
                for table, values in records.items():
                    for value in values:
                        emit(table, value)
                for truth_record in truths:
                    emit("ground_truth", truth_record)
                event_counts[kind] += 1
                hard_counts.update(current_hard)
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
        "showcase": bool(showcase_info),
        "showcase_details": showcase_info,
        "id_scheme": ID_SCHEME,
        "fixture": fixture,
        "difficulty": difficulty,
        "hard_scenarios": dict(hard_counts),
        "rate_multipliers": rate_multipliers,
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
    parser.add_argument("--difficulty", choices=["normal", "hard"], default="normal")
    parser.add_argument("--randomise-rates", action="store_true")
    args = parser.parse_args()
    generate(
        args.out,
        args.rows,
        args.seed,
        args.days,
        args.chunk_size,
        args.config,
        args.fixture,
        args.difficulty,
        args.randomise_rates,
    )


if __name__ == "__main__":
    main()
