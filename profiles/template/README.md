# Profile Setup

1. Copy this directory to a new profile:
   ```bash
   cp -r profiles/template profiles/me
   ```

2. Fill in all three files:
   - `resume.md` — your structured resume (used by the cover letter drafter)
   - `preferences.json` — target roles, locations, skills, blocked companies
   - `cover-letter-style.md` — your voice and tone guidance

3. Point the active symlink at your profile:
   ```bash
   ln -sfn ./me profiles/active
   ```
   On Windows (WSL), symlinks work fine. If you hit issues, set the env var instead:
   ```bash
   echo "ACTIVE_PROFILE_PATH=profiles/me" >> .env
   ```

4. Start the app:
   ```bash
   cp .env.example .env   # add your ANTHROPIC_API_KEY
   docker-compose up
   ```

Your profile directory (`profiles/me/`) is gitignored — it will never be committed.
