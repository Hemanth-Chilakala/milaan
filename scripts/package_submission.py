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
    parser.add_argument("--out", type=Path, default=Path("/workspaces/milaan_final.zip"))
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

## What changed in round two

Shrinking open-item tables, stored reference suffixes and a native Lua SET UDF
improved reconciliation. Frozen blind/hard validation measures ambiguity and
reversals. Daily closes carry open items forward. The branded presentation-mode
dashboard shows live audit snapshots and the 37-payment exception. Bootstrap,
a new-deployment clean checkout and an actual Codespace rebuild were verified.
The documentation, 14-slide deck and private preparation were updated. The old
narrated-video pipeline was removed; an external editor assembles the final video.

## Final measured references

- Unrecorded Phase-A 10M benchmark: **{baseline["seconds"]:.3f} s**, run `{baseline["run_id"]}`.
- Selected recorded month: **{month["seconds"]:.3f} s**, run `{month["run_id"]}`, {month["recording_fps"]} fps.
- Recorded versus Phase-A overhead: **{month["recording_overhead_pct"]:.2f}%**. Every attempt is recorded in metrics.json.
- Recorded daily close: **{day["seconds"]:.3f} s**, run `{day["run_id"]}`.
- Month source membership **{month["score"]["AUTO_MATCH_RATE"] * 100:.3f}%**; link precision **{month["score"]["PRECISION_VALUE"] * 100:.3f}%**, recall **{month["score"]["RECALL_VALUE"] * 100:.3f}%**, {month["score"]["FALSE_POSITIVE"]:,} false links and {month["score"]["FALSE_NEGATIVE"]:,} missed links.
- Normal/blind 1M: 100% precision and recall. Hard 1M: 99.154% precision, 85.872% recall, 3,220 false links and 62,121 missed links.
- Host: 4 cores / 15.62 GiB RAM, Exasol Personal 2026.2.0-nano.3.

README and deck use the unrecorded benchmark. Capture metadata separately states
recording overhead and its actual run. Timers include results, validation and
SQL scoring; explanations and profiling flush follow the core timer. The raw
terminal console is a separate actual unrecorded run, identified in metrics.

## Validation and known gaps

Lint and all 30 unit tests passed. All 10 database tests passed in isolated
verification schemas, preserving the 10M demo; fresh checkout/new deployment
reproduction and the Codespace rebuild passed. Clips were fully decoded,
frame-count and sync-marker checked, and visually reviewed in frame sequences.
Source files and git history were scanned for secrets. The exact staged package
was scanned again before compression. Per-file hashes are in
CHECKSUMS.sha256; the ZIP CRC and extracted local history were verified.

The 60-second month goal was not met. All data is synthetic; bank reversals
expose hard-mode false matches. Split matching is bounded to 12 candidates and
subsets of two or three. Daily/monthly equality was tested on a small fixture;
10M day-by-day replay remains unmeasured. There is no production authentication
or real ledger write-back. macOS/WSL and a newly published Codespace remain
unverified. The optional whole-sequence Lua wrapper and S10 were omitted; the
native Lua SET UDF is included. The final narrated video is intentionally not
included: the editor adds demo.mp4, script.md and credits before submission.

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
            str(ROOT / "private/round2/final-package-secrets.json"),
            "--redact",
            "--no-banner",
        ],
        check=True,
    )
    footprint = sum(p.stat().st_size for p in stage.rglob("*") if p.is_file())
    # Compress on the separate temporary volume, then check actual ZIP headroom.
    pending = stage / "handoff.pending.zip"
    with (ROOT / "private/round2/package-build.log").open("w") as output:
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
    free = shutil.disk_usage(target.parent).free
    if shutil.disk_usage(ROOT).free < 6_000_000_000:
        raise SystemExit("The workspace must retain at least 6 GB free.")
    if free < pending.stat().st_size + 6_000_000_000:
        raise SystemExit(
            f"Need actual ZIP size plus 6 GB reserve: zip={pending.stat().st_size}, free={free}; staging={stage}"
        )
    shutil.copy2(pending, target)
    if target.stat().st_size >= 1_500_000_000:
        raise SystemExit("The ZIP exceeds the 1.5 GB target.")
    with (ROOT / "private/round2/package-crc.log").open("w") as output:
        subprocess.run(
            ["unzip", "-t", str(target)], stdout=output, stderr=subprocess.STDOUT, check=True
        )
    verify = Path(tempfile.mkdtemp(prefix="milaan-zip-verify-"))
    subprocess.run(["unzip", "-q", str(target), "-d", str(verify)], check=True)
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
    (ROOT / "private/round2/final-package-verification.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
