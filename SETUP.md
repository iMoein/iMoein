# GitHub Profile Terminal v7

This version is server-style and removes the old fields.

## Must not appear anymore
- Born
- Life
- PHP
- Oracle APEX
- Repos / Followers / Stars / Forks
- GitHub Stats title

## Included
- Kernel
- Uptime
- UnixTime
- Technical Operations Manager
- Lines.Code / Lines.Added / Lines.Deleted
- Network / Telemetry server-style sections

## Local regenerate

```bash
pip install -r requirements.txt
python scripts/image_to_keyboard_ascii.py assets/profile.png assets/photo-ascii.txt --cols 68
python scripts/generate_profile.py
```

Telemetry now avoids repo/follower/star/fork counters and focuses on line movement.
