# Silent editor capture

Run the recorder from the repository with `PYTHONPATH=.` and the development
requirements installed. Xvfb, ffmpeg and headed Chromium must be available.
Use a warm, reachable Streamlit app at `http://127.0.0.1:8501/?present=1`.

```bash
PYTHONPATH=. python scripts/record_demo.py --shots S01_home_before
PYTHONPATH=. python scripts/record_demo.py --shots S02_run_month_10M \
  --width 1920 --height 1080 --dsf 1 --fps 30
PYTHONPATH=. python scripts/record_demo.py --shots S03_run_today \
  --width 1920 --height 1080 --dsf 1 --fps 30
PYTHONPATH=. python scripts/record_demo.py --shots \
  S04_home_after S05_queue S06_showcase_detail S07_decision S08_accuracy S09_how_it_works
```

S01 resets derived monthly results while retaining source data and audit history.
S02 records a full run; S03 resets and records the daily close. S07 writes an actual
analyst decision. Capture each running shot at 1080p. Idle shots use a 1920×1080
CSS viewport at 2× density, producing 4K footage and stills. Live pass-list stills keep native 1080p density;
completed page states are captured separately at 2× density. No audio is recorded. The audit-write shot uses a 1440p fallback where 4K
misses sampling intervals during the rerender; preserve its 4K evidence still.

If S02 exceeds the Phase-A benchmark by more than 15%, preserve its measurement,
reset the monthly demo, then retry with `--fps 24`. That option disables browser
animation and transitions. Report both observations; it does not change SQL.
Never benchmark or re-encode while recording a reconciliation.

When every shot is finished and the database is idle:

```bash
PYTHONPATH=. python scripts/finish_video_assets.py
PYTHONPATH=. python scripts/export_video_assets.py
PYTHONPATH=. python scripts/review_capture_frames.py
```

The first command re-encodes at slow CRF 18, checks each entire clip by decoding,
probes frames/rate/resolution/audio, and locates the synchronization marker in
actual captured pixels. The second exports current database evidence and checks
that monthly/daily run IDs match the selected clips. The third creates timestamped
contact sheets for visual inspection across each clip. Keep visual review findings
in the external asset manifest. Event timestamps include polling latency.

Assets live beside the repository in `video_assets/`. Commit source and reports
before refreshing exported metrics and running `scripts/package_submission.py`.
The package script includes complete local history, excludes runtime data and
secrets, hashes every file, tests ZIP CRC, extracts it and verifies hashes and git.
The external editor adds the final video, narration script and credits.
