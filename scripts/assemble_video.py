"""Assemble 2:45 footage, offline neural narration and burned-in captions."""

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

        subtitle.write_text(
            "\n\n".join(
                f"{i + 1}\n{timestamp(i * seconds / len(groups))} --> {timestamp((i + 1) * seconds / len(groups))}\n"
                + " ".join(group)
                for i, group in enumerate(groups)
            )
            + "\n"
        )
        clip = folder / f"clip-{index}.mp4"
        caption = f"subtitles={subtitle}:force_style='FontName=DejaVu Sans,FontSize=24,Outline=2,MarginV=30'"
        if isinstance(source, Path):
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
                f"scale=1920:1080,{caption}",
            ]
        else:
            shot = meta["shots"][source]
            length = shot["end"] - shot["start"]
            factor = seconds / length
            label = (
                ",drawtext=text=Time-compressed footage — see actual timer:fontcolor=white:fontsize=28:box=1:boxcolor=0x172b3a:boxborderw=12:x=25:y=25"
                if factor < 0.95
                else ""
            )
            command = [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-ss",
                str(shot["start"]),
                "-t",
                str(length),
                "-i",
                meta["video"],
                "-i",
                str(adjusted),
                "-vf",
                f"setpts={factor}*PTS,fps=30,scale=1920:1080,{caption}{label}",
            ]
        run(
            command
            + [
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-t",
                str(seconds),
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
