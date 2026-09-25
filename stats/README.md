# Telemetry snapshots

The `stats/` directory contains privacy-safe aggregate development telemetry.

## `yesterday.json`

`yesterday.json` is the latest successfully processed daily snapshot. During catch-up it advances through missed local calendar days one commit at a time until it reaches yesterday.

Published fields:

- `date` — snapshot date
- `repos_checked` — owned repositories queried, excluding the profile repository
- `commits` — non-merge commits attributed to the profile owner
- `lines_added` — aggregate Git additions
- `lines_deleted` — aggregate Git deletions
- `net_lines` — additions minus deletions
- `active_repos` — repositories with qualifying commits

## `history.json`

`history.json` stores a rolling daily history used by the analytics dashboard.

The local publisher upserts every processed date and retains up to 400 days. The yearly heatmap uses the most recent 365 days and the bar chart uses the most recent 14 calendar days.

Heatmap intensity is based on:

```text
lines_added + lines_deleted
```

This deliberately ignores empty commits for heatmap intensity.

The initial history can be reconstructed with `scripts/local/backfill_history.py`, which fetches additions/deletions through paginated GitHub GraphQL commit history.

Repository names, file paths, credentials, commit messages, private repository metadata, IP addresses, hostnames, and network details are never written to these public files.
