from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Union
import os, json, base64, uuid
import requests

app = FastAPI()

# --- Scenario endpoint (placeholder; your RAG can remain separate) ---
class Req(BaseModel):
    scenario_id: str

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/load_scenario")
def load_scenario(req: Req):
    # placeholder response; keep as-is for Actions connectivity tests
    return {
        "scenario_id": req.scenario_id,
        "title": f"Scenario: {req.scenario_id}",
        "content": {"ok": True},
    }

# --- Logging payload: matches your chosen schema ---
DecisionRow = List[Union[str, int]]  # ["timestamp","description",ethical,military,command]

class DecisionLog(BaseModel):
    player: str
    unit: str
    decisions: List[DecisionRow]

def github_put_file(repo_full: str, path: str, content_bytes: bytes, message: str):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("Missing GITHUB_TOKEN env var")

    url = f"https://api.github.com/repos/{repo_full}/contents/{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    payload = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode("utf-8"),
    }

    r = requests.put(url, headers=headers, json=payload, timeout=20)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"GitHub write failed: {r.status_code} {r.text}")

@app.post("/append_log")
def append_log(log: DecisionLog):
    repo_full = os.environ.get("LOG_REPO")          # e.g. "youruser/major-plato-logs"
    log_dir = os.environ.get("LOG_DIR", "logs")     # e.g. "logs"
    if not repo_full:
        raise HTTPException(status_code=500, detail="Missing LOG_REPO env var")
    if not os.environ.get("GITHUB_TOKEN"):
        raise HTTPException(status_code=500, detail="Missing GITHUB_TOKEN env var")

    # unique filename to avoid collisions
    file_id = str(uuid.uuid4())[:8]
    # best-effort timestamp from first decision row
    ts = "no-ts"
    if log.decisions and len(log.decisions[0]) >= 1 and isinstance(log.decisions[0][0], str):
        ts = log.decisions[0][0].replace(":", "-")
    safe_player = "".join(c for c in log.player if c.isalnum() or c in ("-", "_"))[:40] or "player"
    filename = f"{safe_player}_{ts}_{file_id}.json"
    path = f"{log_dir}/{filename}"

    content = json.dumps(log.model_dump(), ensure_ascii=False, indent=2).encode("utf-8")
    try:
        github_put_file(
            repo_full=repo_full,
            path=path,
            content_bytes=content,
            message=f"Add decision log {filename}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "logged", "path": path}
