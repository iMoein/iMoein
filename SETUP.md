# GitHub Profile Terminal v9

This version removes the ASCII/photo block completely and replaces it with server-style runtime and GitHub activity telemetry.

## Metrics

- `Uptime`: age shown like a server uptime
- `UnixTime`: timestamp based on birth datetime
- `GitHub.ActiveDays`: number of contribution-calendar days with activity
- `GitHub.FirstActive`: earliest active contribution day found
- `GitHub.DaysOnline`: days elapsed since first active contribution day
- `Lines.Code`: current code lines counted by cloning public repositories and scanning tracked files

## Optional token for better stats

For public repositories, the default `GITHUB_TOKEN` is usually enough. For private repositories or more complete contribution stats, add a repository secret:

```text
PROFILE_STATS_TOKEN
```

Use a GitHub personal access token with read access to the repositories you want included.

## Local regenerate

```bash
pip install -r requirements.txt
python scripts/generate_profile.py
```
