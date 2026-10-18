# Deploy RelayMind to Render (live link for testers)

One Render **Blueprint** creates two services from `render.yaml`:

| Service | What | Plan |
|---|---|---|
| `relaymind` (web, public HTTPS) | Backend + the built UI on one URL, with the reminder worker and Watcher in-process | Starter (always on) |
| `relaymind-falkordb` (private) | FalkorDB, pinned image, 1 GB persistent disk, random password | Starter |

Expected cost: about **$7/month per service + $0.25/GB disk ≈ $15/month**. (The free plan sleeps after inactivity,
which would stop reminders and the Watcher, and free services cannot have a disk.)

## Steps (you do these: they need your account, card and secrets)

1. **Merge to `main`**: the memory PRs (#36 → #38) and the deployment PR. Render deploys from `main`.
2. **Create a Render account** at render.com → *Sign up with GitHub* → allow access to `jay2323-tech/RelayMInd`.
3. **Dashboard → New → Blueprint** → choose the repo → branch `main`. Render reads `render.yaml` and lists both
   services.
4. **Fill in the secrets** Render asks for (never commit them):
   - `RELAYMIND_DEMO_PASSWORD`: the password your testers will type. Pick a new strong one, not your local one.
   - `GEMINI_API_KEY`: your Gemini key (plans need it; answers/memory/work setup work without it).
   - `GROQ_API_KEY`: optional fallback model.
   The database password is generated automatically and shared between the two services.
5. **Apply** and wait for both builds (about 5–10 minutes). On first start the app prepares the database and
   loads the three demo companies (logs show `first start: loading demo companies`).
6. Open `https://relaymind-XXXX.onrender.com`; `/api/health` must answer `{"status": "ok"}`.

## What to send testers (privately)

- The link.
- Accounts (all synthetic): `northstar.lead`, `northstar.peer` (Northstar launch), `harbor.lead` (Harbor route
  change), `aw.quality` (AdventureWorks quality hold).
- The demo password from step 4. Send it separately from the link.

## Operating notes

- **Keep it at one instance.** Logins and the job queue live in the app's memory; a restart signs testers out
  (they just log in again). Data in FalkorDB is kept across restarts and deploys.
- **Reset the demo data**: Render dashboard → `relaymind` → *Shell* → `python scripts/demo_reset.py --scenario all`.
  (This resets the demo companies' records; testers' saved memories and chats stay.)
- **Logs**: `relaymind` → *Logs*. Plans failing with `model_not_configured` means the Gemini key is missing or invalid.
- **Security**: synthetic data only; one shared demo password with login throttling; HTTPS with secure, HTTP-only,
  SameSite=Strict cookies; model keys only on the server; the database has no public address.

## Verified locally before publishing

Both images were built with these exact files and run as a fresh deployment in an isolated Docker network:
first start loaded all three companies; health check passed in ~8 s; UI and SPA routes served; login and wrong
password (401) behaved; factual answer, memory save and cross-chat recall passed the Overseer; a container
restart kept the data ("demo data already present"); the in-process reminder worker reported online.
