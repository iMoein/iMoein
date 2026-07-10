# GitHub Profile Terminal v8

This version fixes line counting.

## What changed

- Removed repo / follower / star / fork counters.
- Removed PHP and Oracle APEX.
- `Lines.Code` is calculated by cloning public repositories and counting tracked code/text files with `git ls-files`.
- `Lines.Added` and `Lines.Deleted` are calculated from GitHub code-frequency stats when GitHub has generated them.
- The script no longer uses the default workflow `GITHUB_TOKEN` for cross-repository stats.
- If GitHub stats are not ready, the SVG shows `sync pending` instead of a misleading `0`.
- A cache file is saved at `assets/code-metrics.json`.

## Optional token for better results

Public repositories should work without a token. For private repositories or higher rate limits, create a GitHub token and add it as this repository secret:

```text
PROFILE_STATS_TOKEN
```

Required permission for public-only stats: public repository read access.
Required permission if you want private repositories included: repository read access.

## Local regenerate without hitting GitHub

```bash
pip install -r requirements.txt
SKIP_GITHUB_FETCH=1 python scripts/generate_profile.py
```

## Full local regenerate

```bash
pip install -r requirements.txt
python scripts/image_to_keyboard_ascii.py assets/profile.png assets/photo-ascii.txt --cols 68
python scripts/generate_profile.py
```
