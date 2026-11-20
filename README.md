# Open Rec

An internal lead-qualification tool for **Simera**. It collects new job postings from Himalayas, uses an LLM (Gemini) to understand each job and score how well Simera's talent covers it, ranks the hiring **companies** as leads with a written reason, and drafts a first outreach message for human review. Nothing is sent from the system.

**Team:** Lilian Abu Ramadan (Team Leader), Nadeen Shadeed, Shaima Kmail, Mohammed Ghanem

## Pipeline

```
1. Discovery      Himalayas API             ->  company, job_posting
2. Understanding  LLM extracts requirements  ->  job_requirement
3. Fit scoring    LLM compares the job with the mock candidate pool -> fit_score + fit_reason
4. Lead scoring   code sums the fit scores of suitable jobs (>= 60) per company -> lead
5. Outreach draft LLM writes a 120-180 word draft for every QUALIFIED lead -> outreach_draft
6. Human review   approve / edit / reject (no send button)
```

## Tech stack

Python, FastAPI, PostgreSQL, SQLAlchemy 2.0 + Alembic, Pydantic, Gemini (Google AI Studio), React + TypeScript, pytest.

## Repository structure

```
backend/
  db/             SQLAlchemy models, database session, Alembic migrations
  discovery/      Stage 1 - job discovery (Himalayas)
  understanding/  Stage 2 - job requirements extraction (LLM)
  fit/            Stage 3 - fit scoring against the mock pool (LLM)
  leads/          Stage 4 - lead scoring (code) + lead reason (LLM)
  drafts/         Stage 5 - outreach drafts (LLM)
  pipeline/       runs all five stages in one command
  api/            FastAPI app and endpoints
  tests/          pytest tests
frontend/         React + TypeScript review interface
.github/          CI workflow (pytest + frontend lint, test, build)
data/             candidates.json (mock candidate data)
docs/             Project report, data contract
```

## Getting started

### 1. Requirements

- **Python 3.11 or newer** (CI uses 3.11)
- **Node.js 22 or newer** (with npm; CI uses 22)
- **PostgreSQL** (running locally)
- A **Gemini API key** from Google AI Studio

### 2. Clone and install the backend

```bash
git clone https://github.com/lilian2005-ui/open-rec-engine.git
cd open-rec-engine
python -m venv .venv
```

Activate the virtual environment:

```bash
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# Mac / Linux
source .venv/bin/activate
```

Then install the packages:

```bash
pip install -r requirements.txt
```

### 3. Create your `.env`

```bash
cp .env.example .env        # Windows: copy .env.example .env
```

Open `.env` and fill in each line:

| Variable | What to put |
|---|---|
| `DATABASE_URL` | Your main PostgreSQL database, e.g. `postgresql+psycopg://postgres:PASSWORD@localhost:5432/openrec` |
| `TEST_DATABASE_URL` | A **separate** database for pytest (its tables are dropped and recreated), e.g. `.../openrec_test` |
| `GEMINI_API_KEY` | Your key from Google AI Studio |
| `LLM_MODEL` | The Gemini model name, e.g. `gemini-3.5-flash-lite` |
| `HIMALAYAS_API_KEY` | Optional. Free Himalayas key; works without it but with lower limits |
| `JWT_SECRET` | A long random text used to sign login tokens. Generate one with the command below |
| `JWT_EXPIRE_MINUTES` | How long a login lasts (default 480 = 8 hours) |
| `CORS_ORIGINS` | Frontend addresses allowed to call the API, as a JSON list. Keep `["http://localhost:5173"]` locally |

Generate `JWT_SECRET`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 4. Set up the database

Create the two empty databases first, as the `postgres` user:

```bash
psql -U postgres -c "CREATE DATABASE openrec;"
psql -U postgres -c "CREATE DATABASE openrec_test;"
```

> **Windows:** if `psql` is "not recognized", either run the same SQL in **pgAdmin** (right-click the server -> Query Tool), or add `C:\Program Files\PostgreSQL\16\bin` to your PATH (Environment Variables -> Path) and open a new terminal.

Then create the tables and load the starting data:

```bash
alembic upgrade head                   # create all tables
python -m backend.db.seed_settings     # default app settings (threshold, limits...)
python -m backend.db.seed_candidates   # mock candidate pool from data/candidates.json
python -m backend.db.create_admin      # asks for name, email and password of the first admin
```

The admin password needs at least 8 characters, with both letters and numbers. It is not shown while you type.

### 5. Run the backend

```bash
uvicorn backend.api.main:app --reload --reload-dir backend
```

Open **http://localhost:8000/docs** to see and try the API.

### 6. Run the frontend

In a second terminal:

```bash
cd frontend
npm install
cp .env.example .env.local     # Windows: copy .env.example .env.local
```

In `frontend/.env.local` set:

```
VITE_USE_MOCK=false
VITE_API_URL=http://localhost:8000
```

Then:

```bash
npm run dev
```

Vite reads `.env.local` only at startup: after any change, stop `npm run dev` (Ctrl+C) and start it again.

Open **http://localhost:5173** and log in with the admin you created in step 4.

### 7. First run

Run the pipeline once to fill the database with jobs, leads and drafts:

- **From the interface:** Settings -> **Run pipeline** (admin only), or
- **From the terminal** (backend folder, venv active):
  ```bash
  python -m backend.pipeline.run --limit 5
  ```
  `--limit 5` keeps the first run small (and cheap on the LLM). With only 5 jobs scored, **0 qualified leads** is normal.

**Scheduled runs:** while the backend is running, a timer checks every 15 minutes whether a run is due. It is off by default (`run_mode = manual`). To turn it on, set `run_mode` to scheduled and choose `run_interval_hours` in Settings. To run once a day at a fixed hour instead, set `run_at_hour` (0-23, Gaza time); any run that started after that hour today, manual or scheduled, counts as today's run. On Render's free plan the server sleeps after 15 minutes without requests, and the timer sleeps with it, so a pinger (for example cron-job.org calling the backend's `/docs` every 10 minutes) keeps it awake.

## Tests

**Backend** (from the project root, venv active). Needs only `TEST_DATABASE_URL`; the LLM is faked in the tests:

```bash
pytest -q
```

**Frontend** (from `frontend/`):

```bash
npm test
npm run lint
npm run build
```

`npm test` uses the fake data. If your `frontend/.env.local` has `VITE_USE_MOCK=false`, set it to `true` first (or delete `.env.local`), otherwise the tests call your real backend and fail.

The same checks run automatically on GitHub for every Pull Request (`.github/workflows/ci.yml`).

## Demo without a backend

The frontend can run alone on fake data from `src/mockData.ts`:

```bash
cd frontend
npm install
npm run dev        # VITE_USE_MOCK=true is the default
```

If you have a `.env.local`, make sure it says `VITE_USE_MOCK=true`, then restart `npm run dev`.

Log in with **`lilian@simera.com`** and **any password**.

## Troubleshooting

| Problem | Fix |
|---|---|
| `psql` is "not recognized" (Windows) | Use pgAdmin (right-click the server -> Query Tool), or add `C:\Program Files\PostgreSQL\16\bin` to PATH and open a new terminal |
| `password authentication failed` | Check the user and password in `DATABASE_URL` in `.env` |
| `create_admin` says "password must contain letters and numbers" | Use at least 8 characters with both letters and numbers |
| The frontend still shows fake data | Set `VITE_USE_MOCK=false` in `frontend/.env.local`, then stop and restart `npm run dev` |
| `npm test` fails with "Invalid email or password" | The tests need fake data: set `VITE_USE_MOCK=true` in `frontend/.env.local` |
| Pipeline prints `503 UNAVAILABLE` | Gemini is busy; the pipeline retries automatically |
| First run shows 0 qualified leads | Normal with `--limit 5`; run without `--limit` for real results |

## How we work

- **Never push directly to `main`.** Every task is done on its own branch and merged through a Pull Request.
- **Branch name = Trello card:** `p0-2-database`, `p1-3-job-understanding`, ...
- **One Pull Request per card.** Put the PR link on the Trello card and move the card to **Review**.
- The **team leader** reviews and merges, then moves the card to **Done**.
- Pull `main` before starting a new branch: `git checkout main && git pull`.
- **Names follow the data contract** (`docs/Open_Rec_Data_Contract_AR_v1.pdf`). Any change to a table or field is made in the contract and the ERD first.
- **Never commit `.env` or API keys.**

## Documents

| File | Content |
|---|---|
| `docs/Open_Rec_Project_Report_v1.pdf` | Requirements, architecture, ERD, wireframes |
| `docs/Open_Rec_Data_Contract_AR_v1.pdf` | Tables, columns, JSON shapes, allowed values |
| `docs/Open_Rec_API_Contract_v1.md` | API endpoints, requests and responses |