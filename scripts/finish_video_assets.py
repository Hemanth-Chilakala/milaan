"""Re-encode idle captures, verify synchronization and publish an editor manifest."""

import argparse
import json
import re
import subprocess
from pathlib import Path

from milaan.config import ROOT
from milaan.demo import is_running
from scripts.record_demo import probe


def marker_frames(path, width, height):
    pixels = subprocess.check_output(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-vf",
            f"crop=2:2:{width // 2}:{height // 2},format=rgb24",
            "-fps_mode",
            "passthrough",
            "-f",
            "rawvideo",
            "-",
        ]
    )
    return [
        i
        for i in range(len(pixels) // 12)
        if pixels[i * 12] > 200 and pixels[i * 12 + 1] < 60 and pixels[i * 12 + 2] > 200
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT.parent / "video_assets")
    parser.add_argument(
        "--verify-existing", action="store_true", help="Verify existing encodes without re-encoding"
    )
    args = parser.parse_args()
    folder = args.out.resolve()
    if is_running():
        raise RuntimeError("Wait for reconciliation before re-encoding.")
    reports = []
    for event_path in sorted(folder.glob("S*.events.json")):
        data = json.loads(event_path.read_text())
        name = data["shot"]
        raw = folder / "raw" / f"{name}.mp4"
        final = folder / data["video_file"]
        final.parent.mkdir(parents=True, exist_ok=True)
        markers = marker_frames(raw, *data["resolution"])
        if not markers:
            raise RuntimeError(f"{name}: no synchronization marker in captured frames")
        data["sync_marker_frame"] = markers[0]
        data["sync_marker_frame_end"] = markers[-1]
        data["sync_marker_video_seconds"] = markers[0] / data["fps"]
        if not args.verify_existing:
            with (folder / "raw" / f"{name}.reencode.log").open("w") as log:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        str(raw),
                        "-an",
                        "-c:v",
                        "libx264",
                        "-threads",
                        "2",
                        "-preset",
                        "slow",
                        "-crf",
                        "18",
                        "-pix_fmt",
                        "yuv420p",
                        "-movflags",
                        "+faststart",
                        *(["-t", "14"] if data.get("output_trim_note") else []),
                        str(final),
                    ],
                    stdout=log,
                    stderr=log,
                    check=True,
                )
        result = probe(final)
        stream = next(s for s in result["streams"] if s["codec_type"] == "video")
        assert len(result["streams"]) == 1 and stream["codec_name"] == "h264"
        duration = float(stream["duration"])
        fps_num, fps_den = stream["avg_frame_rate"].split("/")
        fps = float(fps_num) / float(fps_den)
        frames = int(stream["nb_read_frames"])
        expected = round(duration * data["fps"])
        start_time = float(stream.get("start_time", 0))
        raw_log = (folder / "raw" / f"{name}.ffmpeg.log").read_text()
        dropped = max([int(n) for n in re.findall(r"drop=\s*(\d+)", raw_log)] or [0])
        duplicates = max([int(n) for n in re.findall(r"dup=\s*(\d+)", raw_log)] or [0])
        data["final_probe"] = {
            "duration": duration,
            "frames": frames,
            "fps": fps,
            "expected_frames": expected,
            "frame_count_difference": frames - expected,
            "raw_capture_frame_count_difference": data["raw_probe"]["frame_count_difference"],
            "raw_capture_frames": data["raw_probe"]["frames"],
            "raw_capture_duration": data["raw_probe"]["duration"],
            "start_time": start_time,
            "width": stream["width"],
            "height": stream["height"],
            "bytes": final.stat().st_size,
            "audio_streams": 0,
            "capture_logged_dropped_frames": dropped,
            "capture_logged_duplicate_frames": duplicates,
            "note": "One-frame boundary differences may reflect initial presentation timestamp; no time compression or rate change is used.",
        }
        subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(final), "-f", "null", "-"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        data["full_decode_verified"] = True
        event_path.write_text(json.dumps(data, indent=2) + "\n")
        reports.append(data)
        print(
            f"VERIFIED {name}: {duration:.3f}s, {stream['width']}×{stream['height']}, {frames} frames, sync frame {markers[0]}",
            flush=True,
        )
    manifest = [
        "# Milaan editor assets",
        "",
        "All clips are silent H.264, real time. The magenta sync marker precedes each shot; trim it and align event time zero with its first frame. Event times are observed actions/audit updates, not invented timings. Bounding boxes are in the 1920×1080 CSS viewport; multiply coordinates by the listed scale for video pixels.",
        "",
        "| File | Duration | Resolution | FPS | Frames | Raw/output frame delta | Logged drop/dup | Sync frame | Run ID |",
        "|---|---:|---|---:|---:|---:|---|---:|---|",
    ]
    for r in reports:
        p = r["final_probe"]
        manifest.append(
            f"| {r['video_file']} | {p['duration']:.3f}s | {p['width']}×{p['height']} | {p['fps']:.3f} | {p['frames']} | {p['raw_capture_frame_count_difference']}/{p['frame_count_difference']} | {p['capture_logged_dropped_frames']}/{p['capture_logged_duplicate_frames']} | {r['sync_marker_frame']} | {r['run_id']} |"
        )
    manifest += ["", "## Selected capture observations", ""]
    for report in reports:
        if report.get("output_trim_note"):
            manifest.append(f"- {report['shot']}: {report['output_trim_note']}")
    manifest.append(
        "- Native button/KPI hover tooltips can appear briefly during recorded actions; no editorial labels were added. Core timers stop at the stored result/scoring duration; the live display can continue while explanations are prepared. Both bases are documented in the run events."
    )
    manifest += [
        "",
        "## Files and measurement basis",
        "",
        "- `metrics.json`: database totals, selected month/day runs, 1M normal/blind/hard accuracy, recording attempts and the full showcase. Paise are integers; use Indian rupee formatting.",
        "- `S*.events.json`: click/hover/scroll targets, CSS rectangles, pass observations, run IDs and exact sync marker frame.",
        "- `stills/`: 4K PNG page states and KPI/evidence crops. Mid-run pass-list stills use native 1080p density to avoid altering the recording; their names include native_1080. S01 still is extracted from its native 4K capture; completed month/day states are separate 4K screenshots. Live-run clips are 1080p; idle clips are 4K except the 1440p audit-write fallback. Its evidence still is 4K.",
        "- `recon_console.log`: actual, timestamped `make recon` output from a separate unrecorded run before capture. `console_run.json` records that run.",
        "- `sql_snippets/`: six short source excerpts, including exact matching, batch grouping, the Lua SET call and classification.",
        "- `diagrams/`: editable SVG architecture and real 37-payment settlement arithmetic.",
        "- `brand/`: wordmark, colour tokens, locally served Inter font, OFL licence and app CSS.",
        "- `deck_slides/`: all fourteen slide PNGs at 3840×2160; the deck uses the unrecorded Phase-A benchmark.",
        "",
        "## Recording notes",
        "",
        "Xvfb + headed Chromium app window, cursor hidden, ffmpeg x11grab at nice 19, ultrafast CRF 16; re-encoded at slow CRF 18 only while reconciliation was idle. No soundtrack, captions or editorial overlays are added. The opening magenta marker is required for synchronization, not an editorial overlay. Any retakes and the 24 fps fallback are described in metrics.json. Full clip decoding and frame-count checks were completed. Raw frame-count deficits greater than one indicate missed sampling intervals; constant-rate output may repeat the adjacent frame while preserving real-time duration. Raw and output deltas are both reported. A one-frame difference at a presentation-timestamp boundary is disclosed per event log; frame counts alone do not certify that every rendered browser update was sampled.",
        "",
        "S10 is omitted: Reset/replay is already exercised by S01/S02 and daily capture. The final video, script and credits are produced outside this Codespace.",
        "",
    ]
    (folder / "VIDEO_ASSETS.md").write_text("\n".join(manifest))
    (folder / "capture_verification.json").write_text(
        json.dumps(
            [
                {
                    k: r[k]
                    for k in (
                        "shot",
                        "run_id",
                        "sync_marker_frame",
                        "final_probe",
                        "full_decode_verified",
                    )
                }
                for r in reports
            ],
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
