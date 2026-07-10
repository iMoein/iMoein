# GitHub Profile Terminal

This version fixes the GitHub profile refresh issue by regenerating both:
- `assets/terminal.svg`
- `README.md` with a cache-busting raw GitHub URL

That means the profile overview should refresh much more reliably after each workflow run.

## Local regenerate

```bash
pip install -r requirements.txt
python scripts/image_to_keyboard_ascii.py assets/profile.png assets/photo-ascii.txt --cols 68
python scripts/generate_profile.py
```

## What changed
- Cleaner keyboard-only ASCII portrait
- Bigger portrait on the left
- `Born` removed
- `Life` renamed to `Uptime`
- Role set to `Technical Operations Manager`
- README auto-refreshes with a cache-busting image URL


Latest changes:
- Removed PHP
- Removed Oracle APEX
- Added Kernel line
- Added UnixTime line based on birth datetime
- Kept age-style Uptime
