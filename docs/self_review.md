# Submission review

These are internal estimates against the stated judging rubric, not jury scores.

| Criterion | Estimate / 10 | Evidence and remaining gap |
|---|---:|---|
| Innovation and problem impact | 7 | A specific analyst workflow and realistic reconciliation scenarios; operational impact has not been validated with an NBFC. |
| Effective use of Exasol Personal | 8 | Bulk imports, SQL joins and windows, scalar and SET UDFs, explanations, scoring and native profiling run inside Exasol at 10M source records. The under-one-minute aspiration was not met on the measured host. |
| Technical excellence | 7 | Known-answer fixtures, conflict rejection, measured accuracy and reproducible seeded data; the generator constrains ambiguity and is not a production validation set. |
| Solution design and UX | 8 | A daily-close workflow, responsive layout, evidence comparison, filtered pages and verified analyst decisions; authentication and approved ledger integration are future work. |
| Documentation and reproducibility | 7 | Setup instructions, a clean-checkout/fresh-schema run and local video/deck artifacts; a new Codespace and hosted CI still require publication. |
| Open-source quality | 8 | MIT licence, local phase commits, tests, lint, CI configuration and contributing guidance; external contributors have not reviewed it. |

Three inexpensive improvements were completed: responsive browser review and navigation fixes; per-category false-link scoring with a deliberately wrong-link integration test; and explicit reproduction limits with a fresh-schema check. Next improvements require external evidence: an independently labelled partner dataset, a fresh published Codespace and user feedback from reconciliation analysts.

No industry productivity statistic, production accuracy guarantee or 100M-row throughput claim is made. The public repository and unlisted video mirror are handoff tasks for the publisher.
