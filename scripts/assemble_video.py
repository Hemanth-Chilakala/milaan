"""Assemble 2:45 footage, offline neural narration and burned-in captions."""

import argparse
import json
import subprocess
from pathlib import Path

from milaan.config import ROOT


def run(args):
    subprocess.run(args, check=True)


def duration(path):
    return float(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            text=True,
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segment", type=int, choices=range(7), help="Rebuild one segment")
    selected = parser.parse_args().segment
    folder = ROOT / "private/recording"
    meta = json.loads((folder / "shots.json").read_text())
    segments = json.loads((ROOT / "docs/video/narration.json").read_text())
    model = ROOT / "private/voice/en_US-ljspeech-high.onnx"
    if not model.exists():
        raise RuntimeError("Download the documented public-domain-dataset Piper voice first")
    sources = [
        ROOT / "docs/deck/cards/1.png",
        ROOT / "docs/deck/cards/3.png",
        "reconciliation",
        "review",
        "accuracy",
        "architecture",
        ROOT / "docs/deck/cards/12.png",
    ]
    clips = []
    for index, (segment, source) in enumerate(zip(segments, sources, strict=True)):
        clip = folder / f"clip-{index}.mp4"
        if selected is not None and index != selected:
            if not clip.exists():
                raise RuntimeError("Build the complete video before rebuilding one segment")
            clips.append(clip)
            continue
        seconds = segment["seconds"]
        textfile = folder / f"narration-{index}.txt"
        textfile.write_text(segment["text"])
        audio = folder / f"narration-{index}.wav"
        run(
            [
                str(ROOT / ".venv/bin/python"),
                "-m",
                "piper",
                "--model",
                str(model),
                "--input-file",
                str(textfile),
                "--output-file",
                str(audio),
                "--length-scale",
                "1.1",
            ]
        )
        ratio = duration(audio) / seconds
        if not 0.5 <= ratio <= 2:
            raise RuntimeError("Narration pace is outside acceptable adjustment range")
        adjusted = folder / f"audio-{index}.wav"
        run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-i",
                str(audio),
                "-af",
                f"atempo={ratio},apad",
                "-t",
                str(seconds),
                str(adjusted),
            ]
        )
        subtitle = folder / f"captions-{index}.srt"
        words = segment["text"].split()
        groups = [words[i : i + 13] for i in range(0, len(words), 13)]

        def timestamp(t):
            ms = round(t * 1000)
            return (
                f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
            )

        cues, offset = [], 0
        for number, group in enumerate(groups, start=1):
            start = offset * seconds / len(words)
            offset += len(group)
            end = offset * seconds / len(words)
            cues.append(f"{number}\n{timestamp(start)} --> {timestamp(end)}\n" + " ".join(group))
        subtitle.write_text("\n\n".join(cues) + "\n")
        # Keep captions in a reserved band so they cannot cover dashboard evidence.
        frame = "scale=1920:864:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:44:color=0x142e28"
        caption = f"subtitles={subtitle}:force_style='FontName=DejaVu Sans,FontSize=14,Outline=1,MarginV=14'"
        if isinstance(source, Path):
            video_map = "0:v:0"
            command = [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-loop",
                "1",
                "-i",
                str(source),
                "-i",
                str(adjusted),
                "-vf",
                f"{frame},{caption}",
            ]
        else:
            shot = meta["shots"][source]
            length = shot["end"] - shot["start"]
            factor = seconds / length
            label = (
                ",drawtext=text=Time-compressed footage — see actual timer:fontcolor=white:fontsize=24:x=20:y=10"
                if factor < 0.95
                else ""
            )
            prelude = min(2, shot["start"]) if source == "reconciliation" else 0
            command = [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-ss",
                str(shot["start"] - prelude),
                "-t",
                str(length + prelude),
                "-i",
                meta["video"],
                "-i",
                str(adjusted),
            ]
            if source == "reconciliation":
                # Give both the unreconciled count and completed KPIs time to read.
                work_end = length + prelude - 3
                work_factor = (seconds - 10) / (length - 3)
                filters = (
                    "[0:v]split=3[before][during][after];"
                    f"[before]trim=end={prelude},setpts={5 / prelude}*(PTS-STARTPTS)[opening];"
                    f"[during]trim=start={prelude}:end={work_end},setpts={work_factor}*(PTS-STARTPTS)[work];"
                    f"[after]trim=start={work_end},setpts={5 / 3}*(PTS-STARTPTS)[closing];"
                    "[opening][work][closing]concat=n=3:v=1:a=0,"
                    f"fps=30,{frame},{caption}{label}[visual]"
                )
                command += ["-filter_complex", filters]
                video_map = "[visual]"
            else:
                command += ["-vf", f"setpts={factor}*PTS,fps=30,{frame},{caption}{label}"]
                video_map = "0:v:0"
        run(
            command
            + [
                "-map",
                video_map,
                "-map",
                "1:a:0",
                "-t",
                str(seconds),
                "-r",
                "30",
                "-video_track_timescale",
                "15360",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "28",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "96k",
                "-threads",
                "2",
                str(clip),
            ]
        )
        clips.append(clip)
    listing = folder / "concat.txt"
    listing.write_text("\n".join(f"file '{path}'" for path in clips) + "\n")
    output = ROOT / "docs/video/demo.mp4"
    run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    actual = duration(output)
    if actual > 180 or output.stat().st_size >= 50_000_000:
        raise RuntimeError("Demo exceeds submission limits")
    run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-ss",
            "85",
            "-t",
            "5",
            "-i",
            str(output),
            "-vf",
            "fps=3,scale=640:-1",
            "-loop",
            "0",
            str(ROOT / "docs/video/preview.gif"),
        ]
    )
    print(f"Demo verified: {actual:.2f} seconds; {output.stat().st_size / 1000000:.2f} MB")


if __name__ == "__main__":
    main()
