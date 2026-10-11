"""Build and verify the single local handoff ZIP, including complete git history."""

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from milaan.config import ROOT


def digest(path):
    checksum = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("/workspaces/milaan_final_r3.zip"))
    args = parser.parse_args()
    target = args.out.resolve()
    if target.exists():
        raise SystemExit("The final ZIP already exists; inspect it before replacing it.")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise SystemExit("Commit the final source and reports before packaging.")
    assets = (ROOT.parent / "video_assets").resolve()
    metrics = json.loads((assets / "metrics.json").read_text())
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if metrics["repository_head"] != head:
        raise SystemExit("Refresh editor metrics after the final commit.")
    stage = Path(tempfile.mkdtemp(prefix="milaan-package-"))
    repo = stage / "repo/milaan"
    repo.mkdir(parents=True)
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    forbidden = {
        "data",
        "private",
        ".venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
    }
    for name in filter(None, tracked):
        source = ROOT / name
        if (
            any(part in forbidden for part in Path(name).parts)
            or name.endswith(".csv")
            or name in {".env", "AGENTS.md"}
        ):
            raise SystemExit("A forbidden runtime file is tracked: " + name)
        destination = repo / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    shutil.copytree(ROOT / ".git", repo / ".git")
    shutil.copytree(
        assets,
        stage / "video_assets",
        ignore=shutil.ignore_patterns("raw", "review", "retakes", "__pycache__"),
    )
    prep = stage / "prep"
    prep.mkdir()
    for name in (
        "DEMO_DAY_SCRIPT.md",
        "DEMO_DAY_CHECKLIST.md",
        "QA_PREP.md",
        "HOW_MILAAN_WORKS.md",
        "SHOWCASE_AND_METRICS.md",
    ):
        shutil.copy2(ROOT / "private/prep" / name, prep / name)
    month = metrics["month"]
    baseline = month["unrecorded_benchmark"]
    day = metrics["day"]
    (stage / "README_FIRST.md").write_text(f"""# Milaan final local handoff

The Singleton · Hemanth Chilakala · ExaThon India 2026 · Track 1

## Open these first

- `repo/milaan/README.md`: installation, synthetic data generation and usage.
- `repo/milaan/docs/deck/milaan_deck.pdf`: final 14-slide deck (PPTX also included).
- `video_assets/VIDEO_ASSETS.md`: editor manifest; nine separate silent clips.
- `video_assets/metrics.json`: measured amounts, counts, timings and accuracy.
- `prep/`: private rehearsal, Q&A and SQL walkthrough; do not publish this folder.

## What changed in round three

Seeded realistic identifiers replace sequential showcase IDs. Persistent daily
open items limit the active scope to new arrivals plus unresolved history.
Reference/amount debit-credit reversal pairs are excluded before matching;
a late reversal reopens its previously closed daily group for review.
Dates and navigation are consistent. All nine shots were recaptured with
CPU-affined capture processes and slower polling, using real database runs.
Documentation, slides, screenshots and private preparation use current measurements.

## Current measured references and previous observations

- Unrecorded prepared 10M close: **{baseline["seconds"]:.3f}s**, run `{baseline["run_id"]}`; explicit prior reset **{baseline["reset_before_run_seconds"]:.3f}s**, outside the timer.
- Full unprepared rerun, including open-table restoration: **207.039s**.
- Recorded S02: **{month["seconds"]:.3f}s**, run `{month["run_id"]}` at {month["recording_fps"]} fps; overhead **{month["recording_overhead_pct"]:.2f}%** against the equivalent prepared baseline.
- First-arrival 14 Oct unrecorded: **{day["incremental_unrecorded_benchmark"]["core_matching_seconds"]:.3f}s core**, **{day["incremental_unrecorded_benchmark"]["scoring_validation_seconds"]:.3f}s scoring/validation**, **{day["incremental_unrecorded_benchmark"]["total_seconds"]:.3f}s total**.
- Equivalent same-day replay baseline for S03: **{day["unrecorded_benchmark"]["core_matching_seconds"]:.3f}s core**, **{day["unrecorded_benchmark"]["scoring_validation_seconds"]:.3f}s scoring/validation**, **{day["unrecorded_benchmark"]["total_seconds"]:.3f}s total**.
- Recorded S03: **{day["recorded_s03"]["core_matching_seconds"]:.3f}s core**, **{day["recorded_s03"]["scoring_validation_seconds"]:.3f}s scoring/validation**, **{day["recorded_s03"]["total_seconds"]:.3f}s total**; total overhead **{day["recording_overhead_pct"]:.2f}%**.
- Month membership **{month["score"]["AUTO_MATCH_RATE"] * 100:.3f}%**, precision/recall **100%/100%**, **0 false links**.
- Normal and reused blind: 100% precision and recall. Hard tuned: 100% precision, 85.872% recall. New hard blind seed 20261105: 100% precision, 85.867% recall. All four sets have zero false links.
- Previous identifiers: month 76.144s unrecorded / 114.107s recorded (49.86% overhead). Earlier daily: 47.778s core / 5.669s scoring / 53.447s total. Earlier hard set had 3,220 false links.
- Host: 4 cores / 15.62 GiB RAM, Exasol Personal 2026.2.0-nano.3.

README/deck keep the unrecorded benchmark; actual footage numbers are separately
identified. Timers include preparation, results, conflict validation, commits and
SQL scoring. Explanations/profiling flush follow. The console is a separate
real unrecorded run, not the selected benchmark or recorded run.

## Validation, failures and missed targets

Lint, 34 unit tests and 11 database tests passed. Fixture sequential daily/monthly
links agree across all seven columns. Three consecutive days at 10M scale also
agreed; full 30-day 10M replay remains unmeasured. Reversal testing includes
invalidating a previously closed daily credit and refusing reset on an unclosed
date. Earlier clean checkout/new deployment and container rebuild passed.
Clips were decoded end to end, synchronization/frame-count checked and visually
reviewed. The manifest discloses capture sampling deficits and any retakes.
All files and history were scanned for secrets; the staged package was scanned
again. CHECKSUMS.sha256 covers every packaged file except itself.

The 60s month and 10s daily-core targets were missed: active-set preparation,
classification, result materialisation, validation and scoring remain substantial.
The minimum month goal of under 90s was met only in the prepared starting state.
Capture overhead target was {"met" if month["recording_overhead_pct"] < 20 and day["recording_overhead_pct"] < 20 else "missed"}; measured values above replace estimates.
Hard recall is limited by ambiguous references, long delays and larger splits.
Synthetic validation does not establish production accuracy. Split matching is
bounded to 12 candidates and subsets of two or three. No production authentication
or real ledger write-back exists. macOS/WSL and a newly published Codespace remain
unverified. Whole-sequence Lua wrapper and optional S10 were omitted.

A restart cleared temporary environments/assets and left stale container runtime
state. The pinned environment, CSVs and editor assets were regenerated; stale
runtime state was retired and the same persistent Exasol deployment was restarted.
No retained 10M sources, working database volume or necessary images were removed.
No finished narrated video is included: an external editor adds demo.mp4, script
and credits. The final submission must include that video, at most 3:00.

## Publish and finish outside this Codespace

Publish **only** `repo/milaan/`, including `.git`, to
https://github.com/Hemanth-Chilakala/milaan without squashing or rewriting history.
No remote repository was created or pushed here. Verify hosted CI and a fresh
Codespace, add the editor's final video, then submit using the registration link.
The final video must be at most 3:00. Keep private prep and editor assets out of
the public repository. After downloading, stop this Codespace to save hours;
do not delete it until the published repository is verified.
""")
    checks = []
    for path in sorted(stage.rglob("*")):
        if path.is_file():
            checks.append(f"{digest(path)}  {path.relative_to(stage).as_posix()}")
    (stage / "CHECKSUMS.sha256").write_text("\n".join(checks) + "\n")
    scanner = ROOT / "private/tools/gitleaks"
    if not scanner.is_file():
        raise SystemExit("Install gitleaks in private/tools before final packaging.")
    subprocess.run(
        [
            str(scanner),
            "detect",
            "--no-git",
            "--source",
            str(stage),
            "--report-path",
            str(ROOT / "private/round3/final-package-secrets.json"),
            "--redact",
            "--no-banner",
        ],
        check=True,
    )
    footprint = sum(p.stat().st_size for p in stage.rglob("*") if p.is_file())
    # Compress on the separate temporary volume, then check actual ZIP headroom.
    pending = stage / "handoff.pending.zip"
    with (ROOT / "private/round3/package-build.log").open("w") as output:
        subprocess.run(
            [
                "zip",
                "-r",
                "-9",
                str(pending),
                "README_FIRST.md",
                "CHECKSUMS.sha256",
                "repo",
                "video_assets",
                "prep",
            ],
            cwd=stage,
            stdout=output,
            stderr=subprocess.STDOUT,
            check=True,
        )
    if pending.stat().st_size >= 1_500_000_000:
        raise SystemExit("The ZIP exceeds the 1.5 GB target.")
    with (ROOT / "private/round3/package-crc.log").open("w") as output:
        subprocess.run(
            ["unzip", "-t", str(pending)], stdout=output, stderr=subprocess.STDOUT, check=True
        )
    verify = Path(tempfile.mkdtemp(prefix="milaan-zip-verify-"))
    subprocess.run(["unzip", "-q", str(pending), "-d", str(verify)], check=True)
    for line in (verify / "CHECKSUMS.sha256").read_text().splitlines():
        expected, name = line.split("  ", 1)
        assert digest(verify / name) == expected, name
    extracted = verify / "repo/milaan"
    assert (
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=extracted, text=True).strip()
        == head
    )
    assert not subprocess.check_output(["git", "status", "--porcelain"], cwd=extracted).strip()
    subprocess.run(["git", "log", "-5", "--oneline"], cwd=extracted, check=True)
    old = target.parent / "milaan_final.zip"
    old_bytes = old.stat().st_size if old.is_file() else 0
    free = shutil.disk_usage(target.parent).free
    if free + old_bytes < pending.stat().st_size + 6_000_000_000:
        raise SystemExit(
            f"Need ZIP plus 6 GB reserve after replacing old ZIP: zip={pending.stat().st_size}, free={free}, old={old_bytes}; staging={stage}"
        )
    if old.is_file():
        retired = stage / "previous-handoff.zip"
        shutil.copy2(old, retired)
        assert digest(retired) == digest(old)
        old.unlink()
    shutil.copy2(pending, target)
    assert digest(target) == digest(pending)
    assert shutil.disk_usage(ROOT).free >= 6_000_000_000
    report = {
        "file": str(target),
        "bytes": target.stat().st_size,
        "sha256": digest(target),
        "crc_verified": True,
        "all_file_hashes_verified": True,
        "extracted_history_verified": True,
        "repository_head": head,
        "checked_files": len(checks),
        "source_footprint_bytes": footprint,
        "workspace_free_after_bytes": shutil.disk_usage(ROOT).free,
        "archive_volume_free_after_bytes": shutil.disk_usage(target.parent).free,
    }
    (ROOT / "private/round3/final-package-verification.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
