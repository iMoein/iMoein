# Telemetry snapshots

`yesterday.json` contains privacy-safe, aggregate development activity for the previous local calendar day.

Published fields:

- `date` — snapshot date
- `repos_checked` — owned repositories queried, excluding the profile repository itself
- `commits` — non-merge commits authored by the profile owner
- `lines_added` — aggregate Git additions
- `lines_deleted` — aggregate Git deletions
- `net_lines` — additions minus deletions
- `active_repos` — number of repositories with qualifying commits

Repository names, file paths, credentials, commit messages, and private repository metadata are not written to this file.
