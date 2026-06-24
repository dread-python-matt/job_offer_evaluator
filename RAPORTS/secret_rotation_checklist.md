# Secret Rotation & Git-History Purge Checklist

**Why:** `.env` (with real API keys) and `DATA/user_profile.md` (PII) were committed to git.
They're now untracked + git-ignored, **but they remain in git history**, so the secrets
must be treated as compromised. Removing the files going forward is not enough.

> **Order matters: ROTATE FIRST, then purge.** Purging history does not un-leak a key
> that's already been exposed — rotation is what actually neutralizes it.

---

## Part 1 — Rotate every exposed credential (do this first)

Exposed via committed `.env` (and the working `.env`):

- [ ] **OpenAI API key** (`sk-proj-…`) — platform.openai.com → **API keys** → revoke the
      leaked key → **Create new** → put the new value in `.env` (`OPENAI_API_KEY`).
- [ ] **OpenAI Admin key** (`OPENAI_ADMIN_KEY`) — if you provision a real `sk-admin-…`,
      manage it under **Settings → Organization → Admin keys**; revoke any leaked one.
      (Currently it held a copy of the project key — rotate that too.)
- [ ] **Gemini API key** — Google AI Studio (aistudio.google.com) → **API keys** (or the
      Google Cloud console) → delete the leaked key → create a new one → update
      `GEMINI_API_KEY`.
- [ ] **Postgres password** — it was `password` in `.env`. Change it:
      `ALTER USER <user> WITH PASSWORD '<new-strong-password>';`
      then update `POSTGRES_PASSWORD` and `DATABASE_URL` in `.env`.
- [ ] **Check `docker-compose.yml`** — confirm it reads `${POSTGRES_PASSWORD}` from `.env`
      (not a hardcoded value); restart the DB/containers so the new password takes effect.
- [ ] Verify the app still works with the new values: `uv run pytest` + a manual run.

---

## Part 2 — Purge the secrets from git history

> History rewrite changes **all commit hashes**. Everyone must re-clone afterward, and any
> open PRs/branches need rebasing. Back up the repo (or work on a fresh clone) first.

### Option A — `git filter-repo` (recommended)

```bash
# 1. Install (once)
pip install git-filter-repo            # or: brew install git-filter-repo

# 2. From a FRESH clone of the repo (filter-repo insists on a clean clone)
git clone <repo-url> evaluator-purge && cd evaluator-purge

# 3. Remove the sensitive files from ALL history
git filter-repo --invert-paths --path .env --path DATA/user_profile.md

# 4. Re-add the remote (filter-repo drops it) and force-push every branch + tags
git remote add origin <repo-url>
git push --force --all
git push --force --tags
```

### Option B — BFG Repo-Cleaner

```bash
git clone --mirror <repo-url> evaluator.git
java -jar bfg.jar --delete-files .env --delete-files user_profile.md evaluator.git
cd evaluator.git
git reflog expire --expire=now --all && git gc --prune=now --aggressive
git push --force
```

### Verify the purge

```bash
# Should print nothing if .env is gone from all history:
git log --all --full-history --oneline -- .env
git log --all --full-history --oneline -- DATA/user_profile.md
```

---

## Part 3 — Prevent recurrence

- [x] `.env`, `.env.*` (except `.env.example`) and `DATA/` are git-ignored.
- [x] `.env.example` committed with placeholders only.
- [ ] Confirm no other secrets are tracked: `git ls-files | grep -iE '\.env|secret|credential|\.pem|\.key'`
- [ ] (Optional) add a pre-commit secret scanner (e.g. `gitleaks`, `detect-secrets`).
- [ ] After teammates re-clone, delete the old local clones that still contain the secrets.

---

*Note: if this repo was ever pushed to a remote (GitHub/GitLab/etc.), assume the secrets
were scraped the moment they were public — Part 1 (rotation) is non-negotiable regardless
of the purge.*
