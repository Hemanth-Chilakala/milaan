import csv

import pytest

from generator.generate import HEADERS, generate, load_config


def read(folder, table):
    with (folder / f"{table}.csv").open() as handle:
        return list(csv.DictReader(handle))


def test_deterministic_across_chunk_boundaries(tmp_path):
    a = generate(tmp_path / "a", 1000, chunk_size=19, fixture=True)
    b = generate(tmp_path / "b", 1000, chunk_size=101, fixture=True)
    assert a == b
    for name in HEADERS:
        assert (tmp_path / "a" / f"{name}.csv").read_bytes() == (
            tmp_path / "b" / f"{name}.csv"
        ).read_bytes()


def test_every_break_and_ground_truth_balances(tmp_path):
    manifest = generate(tmp_path, 1000, fixture=True)
    assert set(load_config()["break_rates"]) <= set(manifest["event_counts"])
    assert (
        sum(
            manifest["source_counts"][t]
            for t in ("ledger", "bank_statement", "pg_settlement", "nach_returns")
        )
        == 1000
    )
    truth = read(tmp_path, "ground_truth")
    assert sum(int(t["ledger_paise"]) for t in truth) == manifest["totals"]["ledger_paise"]
    assert sum(int(t["bank_paise"]) for t in truth) == manifest["totals"]["bank_paise"]
    for payment in read(tmp_path, "pg_settlement"):
        assert int(payment["gross_paise"]) - int(payment["fee_paise"]) - int(
            payment["gst_on_fee_paise"]
        ) == int(payment["net_paise"])
        assert int(payment["gst_on_fee_paise"]) == (int(payment["fee_paise"]) * 18 + 50) // 100


def test_configured_rates(tmp_path):
    manifest = generate(tmp_path, 40_000)
    events = manifest["payment_events"]
    for category, probability in manifest["rates"].items():
        expected = probability * events
        assert abs(manifest["event_counts"].get(category, 0) - expected) < 6 * (expected**0.5) + 2


@pytest.mark.parametrize("rows", [1, 2, 3, 99, 100, 101])
def test_exact_row_budget(tmp_path, rows):
    assert generate(tmp_path, rows)["source_rows"] == rows


def test_never_overwrite_existing_dataset(tmp_path):
    generate(tmp_path, 2)
    with pytest.raises(FileExistsError):
        generate(tmp_path, 2)


def test_blind_rates_are_persisted_and_repeatable(tmp_path):
    a = generate(tmp_path / "a", 1000, seed=20261025, randomise_rates=True)
    b = generate(tmp_path / "b", 1000, seed=20261025, randomise_rates=True, chunk_size=17)
    assert a == b
    defaults = load_config()["break_rates"]
    for kind, multiplier in a["rate_multipliers"].items():
        assert 0.5 <= multiplier <= 1.5
        assert a["rates"][kind] == defaults[kind] * multiplier
    assert any(a["rates"][k] != defaults[k] for k in defaults)


def test_hard_mode_truth_balances_and_all_scenarios(tmp_path):
    manifest = generate(tmp_path, 40_000, difficulty="hard", fixture=True)
    assert set(manifest["hard_scenarios"]) == {
        "AMOUNT_DAY_COLLISION",
        "TWO_TYPOS_TRUNCATED_REF",
        "DELAY_T4_T5",
        "FEE_ROUNDING_1_PAISE",
        "SPLIT_4_PLUS",
        "REVERSED_BANK_LINE",
        "DUPLICATED_BANK_LINE",
    }
    truth = read(tmp_path, "ground_truth")
    for total, field in (("ledger_paise", "ledger_paise"), ("bank_paise", "bank_paise")):
        assert sum(int(t[field]) for t in truth) == manifest["totals"][total]
    expected = {t["bank_txn_id"] for t in truth if t["expected_match"] == "1"}
    reversal_originals = {
        t["bank_txn_id"] for t in truth if t["expected_category"] == "BANK_REVERSAL"
    }
    assert not expected & reversal_originals
    bank = read(tmp_path, "bank_statement")
    assert any(int(b["debit_paise"]) > 0 for b in bank)
    assert any(b["bank_txn_id"].endswith("-D") for b in bank)


def test_hard_is_deterministic_and_keeps_exact_budget(tmp_path):
    a = generate(tmp_path / "a", 1001, difficulty="hard", fixture=True, chunk_size=19)
    b = generate(tmp_path / "b", 1001, difficulty="hard", fixture=True, chunk_size=107)
    assert a == b
    assert a["source_rows"] == 1001


def test_realistic_unique_ids_and_middle_showcase(tmp_path):
    import re

    manifest = generate(tmp_path, 40_000, seed=42)
    patterns = {
        "ledger": ("ledger_id", r"SFL-RCT-\d{8}(?:-D)?"),
        "bank_statement": ("bank_txn_id", r"BUB-TXN-\d{8}"),
        "pg_settlement": ("pg_payment_id", r"pf_[A-Za-z0-9]{12}(?:-RF)?"),
        "nach_returns": ("umrn", r"BUB7\d{12}"),
    }
    for table, (column, pattern) in patterns.items():
        values = [row[column] for row in read(tmp_path, table)]
        assert len(values) == len(set(values))
        assert all(re.fullmatch(pattern, value) for value in values)
    showcase = manifest["showcase_details"]
    assert showcase["event_index"] > 0
    batch = [
        r
        for r in read(tmp_path, "pg_settlement")
        if r["settlement_batch_id"] == showcase["batch_id"]
    ]
    assert len(batch) == 37
    assert len({r["order_ref"] for r in batch}) == 37
    assert len({r["gross_paise"] for r in batch}) == 37
    assert all(re.fullmatch(r"SFL-(HL|PL|BL|GL)-\d{7}", r["order_ref"]) for r in batch)
    assert showcase["payment_date"] == "2026-10-27"


def test_batch_namespace_is_independent_per_date():
    from datetime import date

    from generator.generate import Identifiers

    ids = Identifiers(42)
    day = date(2026, 10, 27)
    ids.counters["batch_" + str(day)] = 999_999
    first = ids.batch(day)
    with pytest.raises(ValueError, match="exhausted"):
        ids.batch(day)
    next_day = ids.batch(date(2026, 10, 28))
    assert first != next_day
