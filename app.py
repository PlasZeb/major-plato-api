from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class Req(BaseModel):
    scenario_id: str

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/load_scenario")
def load_scenario(req: Req):
    return {
        "scenario_id": req.scenario_id,
        "title": f"Scenario: {req.scenario_id}",
        "content": {"ok": True}
    }
    
class LogEntry(BaseModel):
    scenario_id: str
    user_id: str | None = None
    decision: str
    justification: str

@app.post("/append_log")
def append_log(entry: LogEntry):
    # később: fájl, DB, MCP, stb.
    print("LOG:", entry)
    return {"status": "logged"}

import os
import psycopg
from datetime import datetime, timezone

def get_conn():
    return psycopg.connect(os.environ["DATABASE_URL"])

def ensure_table():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS decision_logs (
                id SERIAL PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL,
                scenario_id TEXT NOT NULL,
                player TEXT,
                unit TEXT,
                decision TEXT NOT NULL,
                justification TEXT
            )
            """)
        conn.commit()

ensure_table()

@app.post("/append_log")
def append_log(entry: LogEntry):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO decision_logs
                  (created_at, scenario_id, player, unit, decision, justification)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    datetime.now(timezone.utc),
                    entry.scenario_id,
                    entry.player,
                    entry.unit,
                    entry.decision,
                    entry.justification,
                ),
            )
        conn.commit()
    return {"status": "logged"}
