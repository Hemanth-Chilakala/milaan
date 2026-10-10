"""Capture actual timestamped reconciliation output with no browser or recorder."""

import json
import subprocess
from datetime import UTC, datetime

from milaan.config import ROOT
from milaan.db import scope
from milaan.live import snapshot


def main():
    folder = ROOT.parent / "video_assets"
    with (folder / "recon_console.log").open("w") as log:
        log.write(f"{datetime.now(UTC).isoformat()} $ make recon\n")
        log.flush()
        process = subprocess.Popen(
            ["make", "recon"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        for line in process.stdout:
            record = datetime.now(UTC).isoformat() + " " + line
            log.write(record)
            log.flush()
            print(record, end="", flush=True)
        if process.wait() != 0:
            raise SystemExit("The console run failed; inspect recon_console.log")
    with scope("month"):
        state = snapshot()
    (folder / "console_run.json").write_text(json.dumps(state, indent=2) + "\n")


if __name__ == "__main__":
    main()
