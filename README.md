# Resume Review AI — Starter

A minimal AI-powered resume reviewer. This is the starting point for the course.
You will extend it one module at a time.

## Setup

### 1. Install dependencies

```bash
# Frontend
cd frontend
npm install

# Backend (in a new terminal)
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Set up environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in your three keys:
- `ANTHROPIC_API_KEY` — from console.anthropic.com
- `SUPABASE_URL` and `SUPABASE_ANON_KEY` — from your Supabase project settings

### 3. Create the database table

In your Supabase project → SQL Editor, run:

```sql
CREATE TABLE reviews (
  id          uuid        DEFAULT gen_random_uuid() PRIMARY KEY,
  resume_text text        NOT NULL,
  score       integer,
  feedback    text,
  created_at  timestamptz DEFAULT now()
);
```

### 4. Run

```bash
# Terminal 1 — Backend
cd backend
source venv/bin/activate
uvicorn main:app --reload

# Terminal 2 — Frontend
cd frontend
npm run dev
```

Open http://localhost:3000

## Project structure

```
frontend/src/
  types/index.ts          ← data shapes shared with backend
  api/index.ts            ← all fetch calls (edit here for modules 1–3)
  components/
    UploadPanel.tsx       ← file upload (left panel)
    ResultPanel.tsx       ← extracted content + score (right panel)
    HistoryList.tsx       ← past reviews from DB
  styles/global.css       ← all visual design (you won't need to touch this)
  App.tsx                 ← state management, wires components together

backend/
  ai.py                   ← Claude API logic (main file you'll edit)
  db.py                   ← Supabase read/write
  extractor.py            ← PDF/DOCX text extraction
  main.py                 ← FastAPI routes
```

## Course modules

Each module asks you to find and fix one deliberate problem in this starter.
The problems are documented in comments inside `backend/ai.py`.

| Module | Problem | Files to edit |
|--------|---------|---------------|
| 1 | Fragile text parsing | `ai.py` |
| 2 | Score varies every run | `ai.py`, `db.py` |
| 3 | No conversation memory | `ai.py`, `App.tsx` |
| 4 | No bias tracking | `db.py`, `App.tsx` |
| 5 | No evaluation | new `eval.py` |
