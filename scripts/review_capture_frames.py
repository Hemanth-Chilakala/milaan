"""Create timestamped contact sheets for visual inspection of complete captures."""

import json
import subprocess

from milaan.config import ROOT

folder = (ROOT.parent / "video_assets").resolve()
review = folder / "review"
review.mkdir(exist_ok=True)
for event in sorted(folder.glob("S*.events.json")):
    data = json.loads(event.read_text())
    video = folder / data["video_file"]
    if not video.exists() or "final_probe" not in data:
        continue
    duration = data["final_probe"]["duration"]
    interval = max(1, duration / 40)
    count = int(duration / interval) + 1
    rows = (count + 3) // 4
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(video),
            "-vf",
            f"fps=1/{interval},scale=480:270,drawtext=text='%{{pts\\:hms}}':fontsize=14:fontcolor=white:box=1:boxcolor=black@0.7:x=4:y=4,tile=4x{rows}",
            "-frames:v",
            "1",
            str(review / f"{data['shot']}.jpg"),
        ],
        check=True,
    )
    print(data["shot"], flush=True)
