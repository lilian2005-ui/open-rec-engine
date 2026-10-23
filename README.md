# Open Rec

An internal lead-qualification tool for **Simera**. It collects new job postings from Himalayas and Remotive, uses an LLM (Gemini) to understand each job and score how well Simera's talent covers it, ranks the hiring **companies** as leads with a written reason, and drafts a first outreach message for human review. Nothing is sent from the system.

**Team:** Lilian Abu Ramadan (Team Leader), Nadeen Shadeed, Shaima Kmail, Mohammed Ghanem

## Pipeline

```
1. Discovery      Himalayas + Remotive APIs  ->  company, job_posting
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
  discovery/      Stage 1 - source connectors (Himalayas, Remotive)
  understanding/  Stage 2 - job requirements extraction (LLM)
  fit/            Stage 3 - fit scoring against the mock pool (LLM)
  leads/          Stage 4 - lead scoring (code) + lead reason (LLM)
  drafts/         Stage 5 - outreach drafts (LLM)
  api/            FastAPI app and endpoints
  tests/          pytest tests
frontend/         React + TypeScript review interface
data/             candidates.json (mock candidate data)
docs/             Project report, data contract
```

## Getting started

> Steps 3-5 work once tasks P0-2 (database) and P0-7 (settings) are merged.

1. **Clone the repository**
   ```bash
   git clone <repo-url>
   cd <repo-folder>
   ```
2. **Create a virtual environment and install dependencies**
   ```bash
   python -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. **Create your `.env`**
   ```bash
   cp .env.example .env             # then fill in your own values
   ```
4. **Create the database tables**
   ```bash
   alembic upgrade head
   ```
5. **Run the API**
   ```bash
   uvicorn backend.api.main:app --reload
   ```

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
