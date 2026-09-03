# Deploying SkillTrace AI — Vercel (frontend) + Render (backend) + MongoDB Atlas

This app is a single React (CRA + CRACO) frontend and a single FastAPI backend that
talks to MongoDB. On Emergent everything sits behind one origin; on Vercel + Render the
frontend and backend live on **two different domains**, so the only real changes are:

1. The frontend must know the backend's public URL (`REACT_APP_BACKEND_URL`).
2. The backend must allow the frontend's origin (`CORS_ORIGINS`) and use a cloud database
   (`MONGO_URL` -> MongoDB Atlas, since Render has no local MongoDB).

All URLs/secrets are read from **environment variables** — nothing is hardcoded.

> Replace every `YOUR-...` placeholder below with your real values.

---

## STEP 0 — Push the code to GitHub
Use the **"Save to GitHub"** button in the Emergent chat to push this repo to your GitHub
account. Vercel and Render both deploy by connecting to that GitHub repo.

Files already prepared for you in this repo:
- `backend/requirements.txt` — trimmed to only what the app uses (removed `emergentintegrations`
  and the Emergent-internal `litellm` wheel, which would break Render's `pip install`).
- `render.yaml` — Render Blueprint (build/start commands, `$PORT` binding, env var list).
- `frontend/vercel.json` — SPA rewrites so deep links like `/admin` and `/verify/:token`
  don't 404 on refresh.

---

## STEP 1 — Create a free MongoDB Atlas database
1. Go to https://www.mongodb.com/cloud/atlas/register and sign up (free).
2. **Build a Database → M0 Free** shared cluster. Pick any cloud/region near your users.
3. **Database Access → Add New Database User** → username + strong password (save these).
4. **Network Access → Add IP Address → Allow access from anywhere** (`0.0.0.0/0`).
   (Render's outbound IPs are dynamic on the free plan, so allow-all is the simplest option.)
5. **Clusters → Connect → Drivers** → copy the connection string. It looks like:
   ```
   mongodb+srv://YOUR-USER:YOUR-PASSWORD@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```
   Keep this — it's your `MONGO_URL`. (The app reads `DB_NAME` separately, so no DB name is
   needed in the URI.)

---

## STEP 2 — Deploy the backend to Render
### Option A — Blueprint (uses the included `render.yaml`)
1. Render Dashboard → **New → Blueprint** → connect your GitHub repo → Apply.
2. Render reads `render.yaml` and creates a web service `skilltrace-api` with:
   - Root directory: `backend`
   - Build: `pip install -r requirements.txt`
   - Start: `uvicorn server:app --host 0.0.0.0 --port $PORT`
   - Health check: `/api/ml/health`
3. When prompted, fill the env vars marked `sync:false`:
   - `MONGO_URL` = your Atlas string from Step 1
   - `ADMIN_PASSWORD` = a super-admin password you choose (e.g. `Admin@123`)
   - `CORS_ORIGINS` = leave blank for now (set after Step 3 once you know the Vercel URL)
   - `JWT_SECRET` and `PHONE_ENCRYPTION_KEY` are auto-generated — leave them.

### Option B — Manual (without Blueprint)
New → **Web Service** → connect repo → set:
- Root Directory: `backend`
- Runtime: Python 3 · Build: `pip install -r requirements.txt`
- Start: `uvicorn server:app --host 0.0.0.0 --port $PORT`
- Add env vars: `MONGO_URL`, `DB_NAME=skilltrace`, `JWT_SECRET`, `PHONE_ENCRYPTION_KEY`,
  `ADMIN_EMAIL=admin@skilltrace.gov.in`, `ADMIN_PASSWORD`, `CORS_ORIGINS`, `PYTHON_VERSION=3.11.10`.

After the first deploy succeeds, note your backend URL, e.g.:
```
https://skilltrace-api.onrender.com
```
Verify it's live: open `https://skilltrace-api.onrender.com/api/ml/health` → should return `{"status":"ok"...}`.

### Seed the database (one time)
The DB starts empty. In Render → your service → **Shell**, run:
```
python seed.py
```
This creates 5 providers, 10 programs, 150 trainees, and the 4 login accounts. Running it
uses the service's own `PHONE_ENCRYPTION_KEY`, so encryption stays consistent.
> `seed.py` is destructive (it clears collections first) — run it only when you intend to reset demo data.

**Seeded login accounts:**
| Role           | Email                       | Password (from `ADMIN_PASSWORD` for super_admin) |
|----------------|-----------------------------|---------------------------------------------------|
| super_admin    | admin@skilltrace.gov.in     | value you set in `ADMIN_PASSWORD`                 |
| provider       | provider@skilltrace.gov.in  | Provider@123                                      |
| district_admin | district@skilltrace.gov.in  | District@123                                      |
| state_admin    | state@skilltrace.gov.in     | State@123                                         |

> Free Render services sleep after ~15 min idle; the first request after sleep takes ~30–50s to wake.

---

## STEP 3 — Deploy the frontend to Vercel
1. Vercel → **Add New → Project** → import your GitHub repo.
2. **Root Directory:** `frontend`  (click *Edit* and select the `frontend` folder).
3. Framework preset: **Create React App** · Build: `yarn build` · Output: `build`
   (already declared in `frontend/vercel.json`, so defaults are fine).
4. **Environment Variables** → add:
   ```
   REACT_APP_BACKEND_URL = https://skilltrace-api.onrender.com
   ```
   (your Render URL from Step 2, **no trailing slash** — the code also strips one just in case).
5. Deploy. You'll get a URL like `https://YOUR-APP.vercel.app`.

> CRA bakes `REACT_APP_*` vars at **build time**. If you change `REACT_APP_BACKEND_URL`
> later, you must **redeploy** for it to take effect.

---

## STEP 4 — Connect the two (CORS)
1. In Render → `skilltrace-api` → Environment, set:
   ```
   CORS_ORIGINS = https://YOUR-APP.vercel.app
   ```
   (add your custom domain too, comma-separated, if you have one). Save → the service redeploys.
2. Open `https://YOUR-APP.vercel.app`, log in — you're live.

---

## How the pieces map
| Concern            | Emergent (now)                 | Vercel + Render (prod)                          |
|--------------------|--------------------------------|-------------------------------------------------|
| Frontend origin    | preview URL                    | `https://YOUR-APP.vercel.app`                   |
| Backend origin     | same origin, `/api` ingress    | `https://skilltrace-api.onrender.com`           |
| Frontend → backend | `REACT_APP_BACKEND_URL` + `/api` | same (`/api` prefix unchanged)                |
| Database           | local MongoDB (`MONGO_URL`)    | MongoDB Atlas (`MONGO_URL`)                     |
| Port               | 8001 via supervisor            | Render's `$PORT` (start command binds to it)    |
| CORS               | `*`                            | `CORS_ORIGINS` = your Vercel URL                |

## Backend environment variables (reference)
| Var                    | Example / notes                                             |
|------------------------|-------------------------------------------------------------|
| `MONGO_URL`            | `mongodb+srv://user:pass@cluster0.xxxxx.mongodb.net/...`    |
| `DB_NAME`              | `skilltrace`                                                 |
| `JWT_SECRET`           | any long random string (Render auto-generates)              |
| `PHONE_ENCRYPTION_KEY` | any string; must be stable & shared with the seeding run    |
| `ADMIN_EMAIL`          | `admin@skilltrace.gov.in`                                    |
| `ADMIN_PASSWORD`       | your super-admin password                                    |
| `CORS_ORIGINS`         | `https://YOUR-APP.vercel.app`                                |

## Troubleshooting
- **Login "fails" / network error in browser** → almost always `REACT_APP_BACKEND_URL`
  wrong or missing at build time. Open DevTools → Network: the login call must go to
  `https://skilltrace-api.onrender.com/api/auth/login`. If it goes to `undefined/api/...`,
  the env var wasn't set before the Vercel build — set it and **redeploy**.
- **CORS error** in console → `CORS_ORIGINS` on Render doesn't exactly match the Vercel
  origin (scheme + host, no trailing slash).
- **502 / slow first load on Render free** → the service was asleep; retry after ~40s.
- **500 on any DB call** → check `MONGO_URL` and that Atlas Network Access allows `0.0.0.0/0`.
