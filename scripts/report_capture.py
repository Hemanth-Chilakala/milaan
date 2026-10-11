"""Publish selected real-time capture measurements without changing benchmark baselines."""

import json

from milaan.config import ROOT


def main():
    assets = (ROOT.parent / "video_assets").resolve()
    metrics = json.loads((assets / "metrics.json").read_text())
    month, day = metrics["month"], metrics["day"]
    daily = day["recorded_s03"]
    baseline = day["unrecorded_benchmark"]
    summary = (
        f"Selected recorded S02: **{month['recorded_s02_seconds']:.3f}s**, "
        f"**{month['recording_overhead_pct']:.2f}%** above the equivalent prepared "
        f"{month['unrecorded_benchmark']['seconds']:.3f}s month baseline. "
        f"Selected S03: **{daily['core_matching_seconds']:.3f}s core**, "
        f"**{daily['scoring_validation_seconds']:.3f}s scoring/validation**, "
        f"**{daily['total_seconds']:.3f}s total**, "
        f"**{day['recording_overhead_pct']:.2f}%** above the "
        f"{baseline['total_seconds']:.3f}s same-day reset/replay baseline. "
        "These recorded observations are separate from the first-arrival daily close. "
        "Reset preparation and explanation generation remain outside the reconciliation timer."
    )
    section = "\n\n## Selected footage measurements\n\n" + summary + "\n"
    section += (
        f"\nMonth run `{month['run_id']}`; day run `{day['run_id']}`. "
        "Both live shots are 1080p/24 fps. Idle clips are 1440p/30 fps after a 4K test "
        "missed sampling intervals; native 4K page states and evidence crops are supplied separately. "
        "No recording is sped up or replayed. Every selected clip was decoded end to end, "
        "with synchronization markers, frame counts and visual frame sequences checked. "
        "Frame-count deficits and retakes are disclosed in the editor manifest and event logs.\n"
    )
    for name in ["docs/benchmarks.md", "docs/daily.md", "docs/performance.md"]:
        path = ROOT / name
        text = path.read_text().split("\n\n## Selected footage measurements")[0]
        text = text.replace(
            "Fresh capture timings and overhead remain pending; current footage has not been re-recorded.",
            "Current recorded observations are listed below; historical clips were replaced.",
        ).replace(
            "Fresh footage and actual overhead remain pending.",
            "Current recorded observations are listed below.",
        )
        path.write_text(text + section)
    readme = ROOT / "README.md"
    readme.write_text(
        readme.read_text()
        .replace(
            "Fresh recorded timings and overhead are pending the footage checkpoint.",
            summary + " See [capture measurements](docs/capture_results.json).",
        )
        .replace(
            "footage overhead will compare equivalent prepared starting states",
            "footage overhead compares equivalent prepared starting states",
        )
    )
    report = {
        "month": {
            k: month[k]
            for k in [
                "run_id",
                "recorded_s02_seconds",
                "recording_overhead_pct",
                "unrecorded_benchmark",
            ]
        },
        "day": {
            k: day[k]
            for k in [
                "run_id",
                "recorded_s03",
                "recording_overhead_pct",
                "unrecorded_benchmark",
                "incremental_unrecorded_benchmark",
            ]
        },
        "capture_attempts": metrics["capture_attempts"],
        "selected_clip_verification": json.loads(
            (assets / "capture_verification.json").read_text()
        ),
        "console_run_id": metrics["month"]["console_run"]["RUN_ID"],
        "console_seconds": metrics["month"]["console_run"]["ELAPSED_SECONDS"],
    }
    (ROOT / "docs/capture_results.json").write_text(json.dumps(report, indent=2) + "\n")
    config = ROOT / "docs/capture_configuration.md"
    text = config.read_text()
    start = text.find("No new footage has been recorded yet.")
    if start < 0:
        start = text.index("Selected recorded S02:")
    end = text.index("\n\nRecorded total timing", start)
    text = (
        text[:start]
        + summary
        + (
            "\n\nThe below-20% recording-overhead target was "
            + (
                "met"
                if month["recording_overhead_pct"] < 20 and day["recording_overhead_pct"] < 20
                else "missed"
            )
            + ". Previous footage measured 49.86% monthly overhead. Affinity is not exclusive: "
            "capture and Exasol still share a four-core host. Measurements are individual observations, "
            "with warm caches and indexes; the difference cannot be attributed only to the encoder. "
            "All attempted captures and selected frame checks are in [capture_results.json](capture_results.json). "
            "Idle video uses 1440p/30 fps because the 4K test missed sampling intervals; "
            "separate editor stills retain native 4K density."
        )
        + text[end:]
    )
    config.write_text(text)
    for name in ["SHOWCASE_AND_METRICS.md", "QA_PREP.md", "DEMO_DAY_SCRIPT.md"]:
        path = ROOT / "private/prep" / name
        text = path.read_text().split("\n\n## Recorded footage context")[0]
        text = text.replace(
            "Fresh recorded overhead is pending.",
            f"Recorded month overhead is {month['recording_overhead_pct']:.2f}%.",
        ).replace(
            "Fresh footage and overhead are pending.",
            f"Recorded month/day overhead is {month['recording_overhead_pct']:.2f}%/{day['recording_overhead_pct']:.2f}%.",
        )
        path.write_text(text + "\n\n## Recorded footage context\n\n" + summary + "\n")
    print(summary)


if __name__ == "__main__":
    main()
