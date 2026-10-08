# SakhiPune AI

**NLP-Based Personalised Women Empowerment & Support Recommendation System for Pune**

---

## 1. Problem Statement

Women in Pune and Maharashtra often struggle to find the right support — legal aid,
healthcare, counselling, government schemes, shelters, employment opportunities — because
information is scattered across many organisations and portals. A user searching in plain
language gets no single, reliable, locally relevant answer.

---

## 2. Objective

Build an NLP-powered recommendation system that:

- Understands a woman's support need from a plain-language query (English / Hindi / Marathi keywords)
- Classifies the intent (emergency, legal, healthcare, etc.)
- Returns ranked, verified support resources relevant to Pune / Maharashtra
- Provides a real-time webcam demo (future: gesture UI), and an HTML/CSS/JS frontend today

---

## 3. Key Features

| Feature | Detail |
|---|---|
| Intent classification | Keyword-based NLP with spaCy lemmatisation; 10 intent classes |
| 12 support categories | Emergency, Legal, Healthcare, Counselling, Domestic Violence, Employment, Education, Government Schemes, Financial Support, Shelters, Internships, Scholarships |
| 46 verified resources | All from official Pune / Maharashtra government and NGO sources |
| Hybrid data layer | External API → normalise → recommend; on any failure → PostgreSQL fallback |
| TF-IDF ranking | Cosine similarity + intent score + location + language + user preferences |
| Category router | Single entry point maps every intent to the correct category service |
| REST API | FastAPI with Pydantic validation, safe error messages, CORS for local dev |
| Frontend | Plain HTML + CSS + Vanilla JavaScript; no frameworks |
| Multilingual keywords | Hindi and Marathi aliases for employment, education, healthcare |
| Safety | No stack traces / credentials / internal paths ever exposed to the user |

---

## 4. System Architecture

```
Browser (HTML/CSS/JS)
        │
        │  POST /recommend  (or /route, /jobs, /internships, …)
        ▼
FastAPI (uvicorn, 127.0.0.1:8000)
        │
        ├─► Pydantic validation (422 on invalid input)
        │
        ├─► NLP Service
        │     spaCy lemmatise → keyword matching → intent + confidence
        │
        ├─► Category Router
        │     intent + category → correct service loader
        │
        ├─► Category Service  (one per category)
        │     ┌──────────────────────────────────┐
        │     │  *_API_URL set in .env?           │
        │     │  YES → BaseAPIClient.get_json()   │
        │     │        → normalize → is_live=True │
        │     │  NO / FAIL                        │
        │     │       → PostgreSQL query          │
        │     │        → normalize → is_live=False│
        │     └──────────────────────────────────┘
        │
        ├─► Resource Normalizer
        │     ORM row / API payload → common 11-field dict
        │     (name, category, description, location, contact,
        │      url, language, source, source_type, last_updated, is_live)
        │
        ├─► Recommendation Pipeline
        │     TF-IDF vectorise → cosine similarity
        │     + intent score (0.35) + similarity (0.30)
        │     + category (0.15) + preference (0.10)
        │     + location (0.05) + language (0.05)
        │     → ranked list, score, reason
        │
        └─► JSON response → frontend renders resource cards
```

---

## 5. NLP Workflow

```
User text
  │
  ▼
get_tokens(text)
  ├─ lowercase
  ├─ spaCy tokenise
  ├─ remove stop words, punctuation, whitespace
  ├─ lemmatise  (jobs → job, finding → find)
  └─ filter tokens < 2 chars
  │
  ▼
classify_intent(tokens)
  ├─ intersect tokens with each intent's keyword list
  ├─ score = matched / total_keywords  (fraction)
  ├─ also check MULTILINGUAL_INTENT_KEYWORDS (Hindi / Marathi)
  └─ return best-scoring intent, or "general" if no match
```

**Intents and keyword counts (September 2026):**

| Intent | Keywords |
|---|---|
| emergency | 17 |
| legal | 23 |
| healthcare | 29 |
| counselling | 23 |
| domestic_violence | 17 |
| employment | 25 |
| education | 29 |
| government_scheme | 14 |
| financial_support | 28 |
| shelter | 15 |

---

## 6. Recommendation Workflow

```
query + resources
  │
  ├─► TF-IDF vectorise resource texts (name + category + description + keywords)
  ├─► transform query vector
  ├─► cosine similarity per resource
  │
  ├─► intent_score    = 1.0 if resource.category matches detected intent, else 0
  ├─► category_score  = keyword match between category field and query category
  ├─► similarity_score = cosine(query_vector, resource_vector)
  ├─► preference_score = token overlap with user preference answers
  ├─► location_score  = 1.0 (Pune) / 0.6 (Pimpri-Chinchwad) / 0.4 (Online) / 0.0
  ├─► language_score  = 1.0 if resource language matches user language, else 0
  │
  └─► final_score = weighted average (weights: intent 0.35, similarity 0.30,
                    category 0.15, preference 0.10, location 0.05, language 0.05)
                    → sort descending → return top 5
```

---

## 7. API / Data-Source Architecture

No public unauthenticated JSON API exists for any category as of September 2026.
All 10 category services follow the same hybrid pattern:

```python
if CATEGORY_API_URL:                    # set in .env
    try:
        live_data = fetch_with_fallback(client, ...)   # is_live = True
    except (ExternalAPIError, ValueError):
        data = load_from_postgresql(db)                # is_live = False
else:
    data = load_from_postgresql(db)                    # is_live = False
```

When an official API becomes available, add its URL to `.env` — no code changes needed.

Verified sources checked and confirmed web-only (September 2026):

| Category | Source checked | Status |
|---|---|---|
| Education | scholarships.gov.in, mahadbt.maharashtra.gov.in | Institutional login required |
| Employment | ncs.gov.in, mahaswayam.gov.in | Employer login required |
| Internships | sarthi.maharashtra.gov.in | Web-only |
| Healthcare | nhm.gov.in, pmc.gov.in | Web-only |
| Legal | punedlsa.org, legalservices.maharashtra.gov.in | Web-only |
| Financial | mavim.maharashtra.gov.in, pmjdy.gov.in | Web-only |
| Shelter | wcd.gov.in | Web-only |
| Emergency | Helplines 100/108/181/1091 | Static verified numbers |
| Counselling | icallhelpline.org | Web-only |
| Government | womenchild.maharashtra.gov.in, wcd.gov.in | Web-only |

---

## 8. Database

- **Engine:** PostgreSQL 18 (port 5433 on this machine)
- **ORM:** SQLAlchemy 2.x
- **Table:** `support_resources`
- **Records:** 46 verified resources across 11 categories

**Schema:**

```sql
CREATE TABLE support_resources (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    category    VARCHAR(100) NOT NULL,
    description TEXT,
    location    VARCHAR(255),
    contact     VARCHAR(255),
    language    VARCHAR(50)  DEFAULT 'en',
    keywords    TEXT
);
```

**All 46 resources** were sourced from official government portals and established
NGOs: pune.gov.in, punedlsa.org, legalservices.maharashtra.gov.in, nhm.gov.in,
pmc.gov.in, icallhelpline.org, mahaswayam.gov.in, sarthi.maharashtra.gov.in,
ladakibahin.maharashtra.gov.in, mahadbt.maharashtra.gov.in, wcd.gov.in,
womenchild.maharashtra.gov.in, snehalaya.org, pmjdy.gov.in, mavim.maharashtra.gov.in.

No resource names, phone numbers, addresses, URLs or eligibility information
were invented.

---

## 9. Technology Stack

| Layer | Technology | Version |
|---|---|---|
| Language | Python | 3.11 |
| Web framework | FastAPI | 0.111 |
| ASGI server | Uvicorn | 0.29 |
| NLP | spaCy (en_core_web_sm) | 3.7 |
| Data validation | Pydantic v2 | 2.7 |
| ORM | SQLAlchemy | 2.0 |
| Database | PostgreSQL | 18 |
| DB driver | psycopg2-binary | 2.9 |
| ML / ranking | scikit-learn (TF-IDF) | 1.4 |
| Data handling | Pandas, NumPy | 2.2, 1.26 |
| Model persistence | Joblib | 1.4 |
| Settings | pydantic-settings | 2.2 |
| Frontend | HTML5 + CSS3 + Vanilla JS | — |
| Frontend server | Python http.server | built-in |

---

## 10. Project Structure

```
sakhipune-ai/
│
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI app, CORS, error handlers
│   │   ├── api/
│   │   │   └── routes.py              # All API endpoints
│   │   ├── core/
│   │   │   └── config.py              # Settings (pydantic-settings, .env)
│   │   ├── data/
│   │   │   └── resources.csv          # Source data (46 verified resources)
│   │   ├── database/
│   │   │   ├── connection.py          # SQLAlchemy engine + session
│   │   │   └── models.py              # SupportResource ORM model
│   │   ├── models/
│   │   │   └── schemas.py             # Pydantic request/response schemas
│   │   └── services/
│   │       ├── nlp_service.py         # Tokenisation + intent classification
│   │       ├── recommendation_service.py  # TF-IDF scoring + ranking
│   │       ├── tfidf_service.py       # TF-IDF vectoriser helpers
│   │       ├── resource_service.py    # PostgreSQL resource queries
│   │       ├── resource_normalizer.py # Shared ORM→dict normalisation
│   │       ├── category_router.py     # Intent → service mapping
│   │       ├── api_availability.py    # External API status documentation
│   │       ├── api_clients/
│   │       │   └── base_client.py     # BaseAPIClient + fetch_with_fallback
│   │       ├── education_service.py
│   │       ├── jobs_service.py
│   │       ├── internship_service.py
│   │       ├── healthcare_service.py
│   │       ├── legal_service.py
│   │       ├── financial_service.py
│   │       ├── shelter_service.py
│   │       ├── emergency_service.py
│   │       ├── counselling_service.py
│   │       └── government_service.py
│   │
│   ├── evaluation/
│   │   └── intent_evaluation.py       # 36-query hand-labelled eval set
│   ├── tests/                         # 19 test files, 500+ tests
│   ├── load_resources.py              # Load CSV data into PostgreSQL
│   ├── requirements.txt
│   ├── .env                           # Local credentials (not committed)
│   └── .env.example                   # Template
│
└── frontend/
    ├── index.html                     # Single-page application
    ├── css/
    │   └── style.css                  # All styles (no framework)
    └── js/
        ├── app.js                     # API calls, rendering, error handling
        └── questions.js               # Adaptive per-category question flow
```

---

## 11. Setup Instructions

### Prerequisites

- Python 3.10 or 3.11
- PostgreSQL 18 (adjust port in `.env` if different from 5433)
- A terminal / PowerShell

### Step 1 — Install Python dependencies

```powershell
cd sakhipune-ai\backend
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

### Step 2 — Configure the database

Create a PostgreSQL database and user (replace `<your_db_user>` and `<your_db_password>` with your own values):

```sql
-- Run in pgAdmin or psql
CREATE ROLE <your_db_user> WITH LOGIN PASSWORD '<your_db_password>';
CREATE DATABASE sakhipune OWNER <your_db_user>;
```

Copy and edit the environment file:

```powershell
copy .env.example .env
```

Edit `.env` — set `DATABASE_URL` to match your PostgreSQL credentials and port:

```
DATABASE_URL=postgresql://<your_db_user>:<your_db_password>@localhost:<your_db_port>/sakhipune
```

### Step 3 — Load resource data

```powershell
python load_resources.py
```

Expected output:
```
INFO:  Read 46 rows from resources.csv
INFO:  Inserted      : 46
INFO:  Skipped (dupe): 0
INFO:  Failed        : 0
```

### Step 4 — Download the spaCy model (if not already done)

```powershell
python -m spacy download en_core_web_sm
```

---

## 12. Backend Startup

```powershell
cd sakhipune-ai\backend
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

API is available at: **http://127.0.0.1:8000**

Interactive docs: **http://127.0.0.1:8000/docs**

Health check: **http://127.0.0.1:8000/health**

---

## 13. Frontend Startup

```powershell
cd sakhipune-ai\frontend
python -m http.server 8080
```

Open in browser: **http://127.0.0.1:8080**

> The frontend calls `http://127.0.0.1:8000` — both servers must be running.
> CORS is pre-configured for `null` (file://), `localhost:8080`, `127.0.0.1:8080`,
> and all common VS Code Live Server ports.

---

## 14. Environment Variables (.env)

```ini
# Application
APP_NAME=SakhiPune AI
DEBUG=True

# PostgreSQL  (adjust host, port, username, password to match your local setup)
DATABASE_URL=postgresql://<your_db_user>:<your_db_password>@localhost:<your_db_port>/sakhipune

# Frontend CORS origins
FRONTEND_URL=http://localhost:5500
FRONTEND_URL_ALT=http://127.0.0.1:5500

# External API timeout (seconds)
EXTERNAL_API_TIMEOUT_SECONDS=10.0

# External API keys — all empty until a public endpoint is available
EXTERNAL_API_KEY=
EDUCATION_API_URL=
JOBS_API_URL=
INTERNSHIPS_API_URL=
HEALTHCARE_API_URL=
LEGAL_API_URL=
FINANCIAL_API_URL=
SHELTER_API_URL=
EMERGENCY_API_URL=
COUNSELLING_API_URL=
GOVERNMENT_API_URL=
```

**Never commit the real `.env` file.** Use `.env.example` as a template.

---

## 15. API Endpoints

### Core

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check — `{"status": "healthy"}` |
| GET | `/` | Welcome message |
| POST | `/query` | Echo a query (validation only) |
| POST | `/analyze` | Run NLP — return intent + confidence |
| POST | `/recommend` | Full pipeline across all categories |
| POST | `/route` | Universal routed endpoint (NLP → router → service) |
| GET | `/route/explain` | Which service handles intent/category |
| GET | `/api/availability` | External API status for all categories |

### Category endpoints (all follow the same pattern)

| Method | Path | Category |
|---|---|---|
| POST | `/education` | Education + Scholarships |
| POST | `/jobs` | Employment |
| POST | `/internships` | Internships |
| POST | `/healthcare` | Healthcare |
| POST | `/legal` | Legal Support |
| POST | `/financial` | Financial Support |
| POST | `/shelter` | Shelters |
| POST | `/emergency` | Emergency |
| POST | `/counselling` | Counselling |
| POST | `/government` | Government Schemes |

Each category endpoint also has a `GET /<category>/sources` endpoint that returns
data source metadata and live/static status.

### Request body (POST /recommend, /route, /jobs, etc.)

```json
{
  "message": "I am looking for internships in technology",
  "category": "internships",
  "preferences": {
    "interest_area": "Technology",
    "experience_level": "Some experience",
    "work_type": "Open to options"
  },
  "language": "en"
}
```

### Response shape

```json
{
  "message": "I am looking for internships in technology",
  "intent": "employment",
  "confidence": 0.04,
  "match_score": 0.46,
  "recommendations": [
    {
      "id": 0,
      "name": "SARTHI COEP Technical Internship for Women",
      "category": "Internships",
      "description": "SARTHI runs advanced technical training at COEP Pune...",
      "location": "College of Engineering Pune – Shivajinagar Pune",
      "contact": "https://sarthi.maharashtra.gov.in",
      "language": "en",
      "score": 0.4647,
      "reason": "Recommended because it matches your support need...",
      "url": "https://sarthi.maharashtra.gov.in",
      "source": "PostgreSQL verified data",
      "source_type": "database",
      "last_updated": "",
      "is_live": false
    }
  ]
}
```

---

## 16. Testing

Run all tests (requires PostgreSQL running):

```powershell
cd backend
python -m pytest tests/ -q
```

Run specific test groups:

```powershell
# NLP intent classification (no DB needed)
python -m pytest tests/test_nlp.py -q

# Ranking + system tests (requires DB)
python -m pytest tests/test_ranking_and_system.py -q

# API failure / security tests (no live network)
python -m pytest tests/test_api_failure.py -q

# All unit tests except live-server tests
python -m pytest tests/ --ignore=tests/test_frontend.py --ignore=tests/test_nlp_evaluation.py -q
```

**Test counts (as of Day 30):**

| Test file | Tests | Coverage |
|---|---|---|
| test_nlp.py | 96 | Preprocessing, all intents, edge cases |
| test_nlp_evaluation.py | 179 | 13 intents × queries, multilingual, eval metrics |
| test_recommendation_ranking.py | 12 | Scoring signals, weights, location, language |
| test_ranking_and_system.py | 55 | 12 categories end-to-end, all edge cases |
| test_api_client.py | 24 | Transport errors, fallback, normalisation |
| test_hybrid_fallback.py | 87 | All 10 services × 8 failure modes |
| test_api_failure.py | 67 | All HTTP errors, security leak checks |
| test_resource_normalizer.py | 27 | ORM→dict, validate, compatibility |
| test_category_router.py | 28 | All intent→service mappings |
| test_jobs_service.py | 21 | Employment service |
| test_internship_service.py | 21 | Internship service |
| test_healthcare_service.py | 20 | Healthcare service |
| test_legal_service.py | 20 | Legal service |
| test_financial_service.py | 20 | Financial service |
| test_api_errors.py | 7 | Route-level error handling |
| test_schemas.py | 9 | Pydantic validation |
| test_similarity.py | 4 | TF-IDF cosine similarity |
| test_tfidf.py | 7 | TF-IDF vectoriser |

**NLP evaluation results (36-query hand-labelled dataset, run via pytest):**

```
Accuracy  : 100.0%  (36/36 after bug fixes)
Macro F1  : 1.000
Weighted F1: 1.000
```

---

## 17. Limitations

1. **No live external APIs** — All 10 category services are in PostgreSQL-fallback mode.
   Every result has `is_live: false`. When an official API becomes available, set the
   corresponding `*_API_URL` in `.env`.

2. **46 resources only** — The database contains a curated set of 46 verified resources.
   It does not cover every organisation in Pune.

3. **Keyword-based NLP** — The classifier uses keyword matching, not ML classification.
   Queries that use unusual phrasing may not match the expected intent.

4. **English-first** — Full spaCy preprocessing is English-only. Hindi/Marathi support
   is limited to explicit keyword aliases in `MULTILINGUAL_INTENT_KEYWORDS`.

5. **PostgreSQL dependency** — The application starts and NLP endpoints work without
   a database, but recommendations require PostgreSQL.

6. **No authentication** — The sign-in modal is a browser-session-only UI convenience;
   it stores only a name in `sessionStorage` and performs no real authentication.

---

## 18. Safety & Data Verification Notes

- **No fabricated data** — Every resource name, phone number, address, URL and description
  was sourced from official government portals or established organisations.
  Nothing was invented.

- **No credentials exposed** — Stack traces, database URLs, API keys, passwords, and
  internal file paths are never returned in any HTTP response body. All error responses
  follow the shape `{"error": "...", "message": "user-friendly text"}`.

- **Emergency safety** — Emergency and shelter endpoints include safety notes directing
  users to call 100 (Police) or 112 (National Emergency) for immediate danger.
  The system explicitly states it provides *information* only.

- **is_live flag** — Every resource clearly states whether it came from a live API call
  (`is_live: true`) or from verified PostgreSQL data (`is_live: false`). No static data
  is ever presented as real-time.

---

## 19. HCI Gesture Recognition (Planned)

A separate hand gesture recognition module (`hand_gesture_recognition/`) is
scaffolded for the EAI lab component. It uses:

- MediaPipe Hands (21-landmark feature extraction)
- Random Forest classifier (scikit-learn)
- OpenCV webcam capture

**Gestures → HCI Commands:**

| Gesture | Command |
|---|---|
| Open Palm | STOP / PAUSE |
| Fist | SELECT |
| Thumbs Up | CONFIRM |
| Victory | NEXT |
| Pointing | POINT / SELECT |

This module is independent of the SakhiPune AI web application.

---

*Built for TY B.Tech CSE (AI & ML) — NLP Project, Pune — September 2026*
