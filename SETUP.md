# GitHub Profile Terminal

This profile banner uses a real keyboard-character ASCII portrait.

## Update

```bash
pip install -r requirements.txt
python scripts/generate_profile.py
```

## Replace the photo and regenerate the keyboard ASCII

```bash
python scripts/image_to_keyboard_ascii.py assets/profile.png assets/photo-ascii.txt --cols 82
python scripts/generate_profile.py
```

## GitHub Profile README

Create a public repository with the exact same name as your GitHub username, then put these files in it.

No email or Discord fields are included.
LinkedIn is set to: https://www.linkedin.com/in/moeinghezelbash/
