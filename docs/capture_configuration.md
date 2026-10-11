# Capture configuration

Live-run shots use 1920 × 1080 at 24 fps. Xvfb, Chromium and the live ffmpeg encoder inherit CPU affinity for core 3. The script verifies available affinity indices and records the chosen core in shot metadata; affinity limits capture placement but does not reserve that core exclusively.

Capture mode sets the dashboard and event observation interval to 1.0 second. Chromium disables GPU rendering and smooth scrolling; all other tabs are closed. CSS disables continuous animations except the running-pass spinner. No cursor or browser chrome is recorded. Static shots retain their existing native density, sync marker and event-log method.

Selected recorded S02: **111.801s**, **26.72%** above the equivalent prepared 88.229s month baseline. Selected S03: **37.280s core**, **11.325s scoring/validation**, **48.611s total**, **20.79%** above the 40.244s same-day reset/replay baseline. These recorded observations are separate from the first-arrival daily close. Reset preparation and explanation generation remain outside the reconciliation timer.

The below-20% recording-overhead target was missed. Previous footage measured 49.86% monthly overhead. Affinity is not exclusive: capture and Exasol still share a four-core host. Measurements are individual observations, with warm caches and indexes; the difference cannot be attributed only to the encoder. All attempted captures and selected frame checks are in [capture_results.json](capture_results.json). Idle video uses 1440p/30 fps because the 4K test missed sampling intervals; separate editor stills retain native 4K density.

Recorded total timing comes from committed database audit snapshots. Daily core matching, scoring/validation and total timing are separate audit fields. Explanations follow the reconciliation timer. Event timestamps reflect the observation interval and must not be interpreted as sub-second pass-start accuracy.
