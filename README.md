# ADCEA – Analytics, Data Cleaning & Easy AutoML

This repository contains a small, production-style FastAPI + vanilla JS application:

- **Upload & profile** CSV datasets
- **Clean** data with simple, robust defaults
- **Engineer features** from numeric / datetime / text columns
- **Train** a baseline scikit-learn model asynchronously
- **Inspect** the latest run via an embedded HTML **report**
- **Download** trained models as `.joblib` files

The app is intentionally framework-light to keep deployment and debugging straightforward.

---

## 1. Quickstart

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

uvicorn backend.main:app --reload --port 8000
```

Then open your browser at: <http://127.0.0.1:8000/>

> The single-page UI is served from `frontend/dist/` by FastAPI. No Node.js build
> step is required – the bundle is already included.

---

## 2. Core Endpoints

### Auth

- `POST /auth/register` – JSON `{ "email": "...", "password": "..." }`
- `POST /auth/login` – same payload, returns `{ user, token }`
- `GET /auth/me` – requires `Authorization: Bearer <token>`

Users are stored in a small SQLite DB: `backend_auth.db` (path configurable via
`ADCEA_AUTH_DB`). Passwords are hashed using `bcrypt`, tokens are JWTs signed
with `ADCEA_JWT_SECRET`.

### Data utilities

- `POST /api/upload` – CSV → basic profile (rows, cols, dtypes, missing, preview)
- `POST /api/clean` – CSV → cleaned CSV + summary (and writes `cleaned.csv`)
- `POST /api/features` – CSV → engineered features, feature importance sample,
  and writes `features.parquet`

### Training

- `POST /api/train/start` – multipart form with:
  - `file` – CSV (must contain the target column)
  - `target` – target column name (defaults to `target`)
- `GET /api/train/status/{job_id}` – latest training status, metrics, epoch history
- `GET /api/models` – list of saved `.joblib` models
- `GET /api/models/{model_name}/download` – download a specific model file
- `GET /api/report` – HTML report for the most recent successful job

Training runs in a background thread (`ThreadPoolExecutor`). Models are stored
inside the `models/` folder created at runtime.

---

## 3. Frontend Overview

The SPA is a small vanilla JS application in `frontend/dist/assets/main.js`:

- Uses `location.hash` routing (`#/analysis`, `#/train`, `#/models`, `#/report`, `#/login`, `#/register`, `#/me`)
- Persists JWT tokens in `localStorage` under the key `adcea_token`
- Uses [Chart.js](https://www.chartjs.org/) (via CDN) for an epoch metric chart on
  the **Train** tab and inside the embedded **Report** view
- Handles API errors gracefully with visible error banners instead of crashing

If you want to replace this with a React or other framework-based frontend, you
can keep the API exactly as-is and swap out `frontend/dist/`.

---

## 4. Configuration

Environment variables:

- `ADCEA_JWT_SECRET` – secret key for signing JWTs (default: `"change_this_secret"`)
- `ADCEA_AUTH_DB` – path to the SQLite auth DB (default: `./backend_auth.db`)
- `ADCEA_JWT_EXPIRE_MIN` – access token expiry, in minutes (default: 10080 = 7 days)

---

## 5. Notes

- The project is intentionally simple but structured to resemble a small
  production service (auth layer, service modules, async jobs, SPA UI).
- For real-world use, you should:
  - set a strong `ADCEA_JWT_SECRET`
  - lock down CORS to your real frontend origin
  - move models / data to a persistent volume or object storage
