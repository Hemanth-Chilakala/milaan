# Capture configuration

Live-run shots use 1920 × 1080 at 24 fps. Xvfb, Chromium and the live ffmpeg encoder inherit CPU affinity for core 3. The script verifies available affinity indices and records the chosen core in shot metadata; affinity limits capture placement but does not reserve that core exclusively.

Capture mode sets the dashboard and event observation interval to 1.0 second. Chromium disables GPU rendering and smooth scrolling; all other tabs are closed. CSS disables continuous animations except the running-pass spinner. No cursor or browser chrome is recorded. Static shots retain their existing native density, sync marker and event-log method.

No new footage has been recorded yet. The below-20% recording-overhead target remains unassessed. Previous footage measured 49.86% monthly overhead. The new comparison must use equivalent starting states: the month after an explicit demo reset and the daily shot as a same-day replay after reset. Reset preparation is separately reported. The first incremental 14 Oct arrival close is a separate operational measurement.

Recorded total timing comes from committed database audit snapshots. Daily core matching, scoring/validation and total timing are separate audit fields. Explanations follow the reconciliation timer. Event timestamps reflect the observation interval and must not be interpreted as sub-second pass-start accuracy.
