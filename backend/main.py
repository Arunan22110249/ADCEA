"""FastAPI backend for ADCEA."""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Optional, Dict, Any

import pandas as pd
from fastapi import (
    FastAPI,
    UploadFile,
    File,
    HTTPException,
    Depends,
    Header,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from backend.services.data_profiler import profile_df
from backend.services.data_cleaner import clean_df
from backend.services.feature_engineer import engineer_features
from backend import auth, train as train_module

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIST = os.path.normpath(os.path.join(BASE_DIR, "..", "frontend", "dist"))

app = FastAPI(title="ADCEA")

# CORS for local dev; for production, tighten this list.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_token(authorization: Optional[str] = Header(default=None)) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


async def get_current_user(
    authorization: Optional[str] = Header(default=None),
) -> Optional[Dict[str, Any]]:
    token = _get_token(authorization)
    if not token:
        return None
    payload = auth.decode_token(token)
    if not payload:
        return None
    user_id = int(payload.get("sub"))
    return auth.get_user_by_id(user_id)


# -------- Auth endpoints ---------


@app.post("/auth/register")
async def register(data: Dict[str, str]):
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""
    if not email or not password:
        raise HTTPException(status_code=400, detail="email and password are required")
    try:
        user = auth.create_user(email, password)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    token = auth.issue_access_token(user)
    return {"user": {"id": user["id"], "email": user["email"]}, "token": token}


@app.post("/auth/login")
async def login(data: Dict[str, str]):
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""
    user = auth.verify_user(email, password)
    if not user:
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = auth.issue_access_token(user)
    return {"user": {"id": user["id"], "email": user["email"]}, "token": token}


@app.get("/auth/me")
async def me(user=Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="unauthenticated")
    return {"id": user["id"], "email": user["email"], "created_at": user["created_at"]}


# -------- Data utilities ---------


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="only CSV files are supported")
    raw = await file.read()
    df = pd.read_csv(io.BytesIO(raw))
    profile = profile_df(df)
    return profile


@app.post("/api/clean")
async def clean(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="only CSV files are supported")
    raw = await file.read()
    df = pd.read_csv(io.BytesIO(raw))
    cleaned, summary = clean_df(df)
    out_path = os.path.join(os.getcwd(), "cleaned.csv")
    cleaned.to_csv(out_path, index=False)
    summary["download"] = out_path
    return summary


@app.post("/api/features")
async def features(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="only CSV files are supported")
    raw = await file.read()
    df = pd.read_csv(io.BytesIO(raw))
    feats, scores = engineer_features(df)
    out_path = os.path.join(os.getcwd(), "features.parquet")
    feats.to_parquet(out_path, index=False)
    # return a small scores sample to avoid huge payloads
    scores_sample = dict(list(scores.items())[:20])
    return {
        "n_features": int(feats.shape[1]),
        "scores_sample": scores_sample,
        "download": out_path,
    }


# -------- Training endpoints (protected) ---------


@app.post("/api/train/start")
async def train_start(
    request: Request,
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    if not user:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)

    form = await request.form()
    target = form.get("target") or "target"

    raw = await file.read()
    job_id = train_module.start_training_from_bytes(raw, target)
    return {"job_id": job_id}


@app.get("/api/train/status/{job_id}")
async def train_status(job_id: str, user=Depends(get_current_user)):
    if not user:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    job = train_module.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.get("/api/models")
async def list_models(user=Depends(get_current_user)):
    if not user:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    models = []
    model_dir = Path(train_module.MODEL_DIR)
    for p in model_dir.glob("*.joblib"):
        models.append({"name": p.name, "path": str(p)})
    return models


@app.get("/api/models/{model_name}/download")
async def download_model(model_name: str, user=Depends(get_current_user)):
    if not user:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    p = os.path.join(train_module.MODEL_DIR, model_name)
    if not os.path.exists(p):
        raise HTTPException(status_code=404, detail="model not found")
    return FileResponse(p, media_type="application/octet-stream", filename=model_name)


@app.get("/api/report")
async def report(user=Depends(get_current_user)):
    if not user:
        return HTMLResponse(
            "<h2>Unauthorized</h2><p>Please log in to view reports.</p>",
            status_code=401,
        )

    # Choose latest job
    latest_job = None
    for job_id, job in train_module.JOBS.items():
        if job.get("status") == "completed":
            if not latest_job or job["completed_at"] > latest_job["completed_at"]:
                latest_job = job.copy()
                latest_job["job_id"] = job_id

    if not latest_job:
        return HTMLResponse(
            "<h2>No completed jobs yet</h2><p>Start a training run first.</p>"
        )

    # Render a simple HTML view
    metrics = latest_job.get("metrics", {})
    epoch_history = latest_job.get("epoch_history", [])

    html = f"""
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8" />
        <title>ADCEA Report</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
          body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
                 margin: 0; padding: 1.5rem; background: #0b1020; color: #f5f5f5; }}
          h1 {{ margin-bottom: 0.25rem; }}
          .muted {{ color: #a0aec0; font-size: 0.9rem; }}
          .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                   gap: 1.5rem; margin-top: 1.5rem; }}
          .card {{ background: #141a33; border-radius: 12px; padding: 1rem 1.25rem;
                   box-shadow: 0 10px 25px rgba(0,0,0,0.35); }}
          .metric {{ font-size: 1.75rem; font-weight: 600; }}
          .metric-label {{ font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.08em; color: #a0aec0; }}
        </style>
      </head>
      <body>
        <h1>Latest Training Report</h1>
        <div class="muted">Job ID: {latest_job["job_id"]} &nbsp;•&nbsp; Target: {latest_job.get("target","")} </div>

        <div class="grid">
          <div class="card">
            <div class="metric-label">Model Type</div>
            <div class="metric">{metrics.get("model_type","–")}</div>
          </div>
          <div class="card">
            <div class="metric-label">Rows / Cols</div>
            <div class="metric">{latest_job.get("rows","?")} / {latest_job.get("cols","?")}</div>
          </div>
          <div class="card">
            <div class="metric-label">Primary Metric</div>
            <div class="metric">
            {metrics.get("accuracy") or metrics.get("roc_auc") or metrics.get("rmse") or "–"}
            </div>
          </div>
        </div>

        <div class="grid" style="margin-top:2rem;">
          <div class="card">
            <h3>Epoch History</h3>
            <canvas id="epochChart" height="140"></canvas>
          </div>
          <div class="card">
            <h3>Confusion / Error</h3>
            <pre style="font-size:0.75rem; white-space:pre-wrap;">{metrics}</pre>
          </div>
        </div>

        <script>
          const epochs = {epoch_history};
          const labels = epochs.map(e => e.epoch);
          const values = epochs.map(e => e.metric);
          const ctx = document.getElementById('epochChart').getContext('2d');
          new Chart(ctx, {{
            type: 'line',
            data: {{
              labels,
              datasets: [{{
                label: 'Metric',
                data: values,
                fill: false,
              }}]
            }},
            options: {{
              responsive: true,
              plugins: {{
                legend: {{
                  display: false
                }}
              }},
              scales: {{
                x: {{ title: {{ display: true, text: 'Epoch' }} }},
                y: {{ title: {{ display: true, text: 'Score' }}, min: 0, max: 1 }}
              }}
            }}
          }});
        </script>
      </body>
    </html>
    """
    return HTMLResponse(html)


# --------- Frontend static hosting ----------

if os.path.isdir(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")


@app.get("/")
async def root():
    index_path = os.path.join(FRONTEND_DIST, "index.html")
    if not os.path.exists(index_path):
        return JSONResponse({"message": "Frontend not built"}, status_code=500)
    return FileResponse(index_path)
