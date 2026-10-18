# Free deployment: Hugging Face Docker Space (no card)

One free Space runs everything in ONE container: FalkorDB (localhost only, random password), the backend and the
built UI. Free "CPU basic" hardware: 2 vCPU, 16 GB RAM. It sleeps after 48 hours without visitors and wakes when
someone opens it. Pause or delete it anytime from the Space settings.

**Trade-off:** data lives inside the container. Each restart/wake reloads the three demo companies, so testers'
memories, plans and approvals from before the restart are not kept. Fine for a demo; use `docs/deploy-render.md`
(paid) if you need persistence.

## Steps (you do these: your account and secrets)

1. **Create a free account** at huggingface.co (no card).
2. **New Space** (huggingface.co/new-space): name `relaymind`, SDK **Docker** → *Blank*, hardware **CPU basic
   (free)**, visibility **Public** (testers need to open it; the code you push becomes visible, secrets do not).
3. **Add secrets** in the Space → *Settings* → *Variables and secrets* → *New secret*:
   - `RELAYMIND_DEMO_PASSWORD`: a new simple password (it is SHOWN on the login screen; don't reuse a real one)
   - `GEMINI_API_KEY`: your Gemini key (plans need it; answers/memory/work setup work without it)
   - `GROQ_API_KEY`: optional fallback
4. **Create an access token**: huggingface.co/settings/tokens → *New token* → type **Write**.
5. **Prepare and push the Space** from the RelayMind folder:
   ```
   .venv/Scripts/python scripts/export_hf_space.py ../relaymind-hf
   cd ../relaymind-hf
   git remote add space https://huggingface.co/spaces/<your-username>/relaymind
   git push --force space main
   ```
   When asked, username = your Hugging Face username, password = the **token** from step 4.
6. The Space builds (5–10 min, watch *Logs*). Open the app at **`https://<your-username>-relaymind.hf.space`**
   (the direct address, not the embedded view on huggingface.co, which blocks the secure sign-in cookie).

## Share with testers

The direct `.hf.space` link. The login screen lists the demo accounts and shows the password (public demo mode is
on in this image).

## Update later

Re-run step 5 into a fresh folder (or copy changed files into `../relaymind-hf`, commit, push).

## Safety

Synthetic data only. Anyone with the link can sign in. The AI usage cap (60 calls/user/hour, 300 total) protects
your Gemini quota. FalkorDB is never reachable from outside the container.
