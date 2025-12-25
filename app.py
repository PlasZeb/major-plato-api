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
