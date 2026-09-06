from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Union
import os, json, base64, uuid, secrets
import requests

app = FastAPI()

# --- Scenario endpoint (placeholder; your RAG can remain separate) ---
# --- Scenario database and endpoints ---

class Req(BaseModel):
    scenario_id: str


SCENARIOS = {
    "bridge_guardian": {
        "title": "Exercise Bridge Guardian",
        "content": {
            "environment": "peacekeeping",
            "operational_area": "The fictional state of Veloria",
            "mission": (
                "Secure the bridge connecting the command post with the village "
                "while protecting civilians and maintaining freedom of movement."
            ),
            "commanders_intent": (
                "Keep the crossing operational, prevent armed groups from gaining "
                "control of it, and avoid unnecessary escalation."
            ),
            "objectives": [
                "secure the bridge",
                "protect the civilian population",
                "maintain access between the command post and the village",
                "identify armed actors before using force"
            ],
            "known_facts": [
                "Civilians are still using the bridge.",
                "An unidentified armed group has been observed near the village.",
                "Intelligence regarding the group's intentions is incomplete.",
                "A medical convoy is expected to approach the crossing."
            ],
            "constraints": [
                "limited use of force",
                "positive identification required",
                "civilian protection has priority",
                "human authorization required for escalation"
            ],
            "cultural_context": {
                "description": (
                    "The village contains a mosque and a small interfaith medical "
                    "clinic. Local religious and community leaders have requested "
                    "advance coordination before military searches."
                ),
                "training_focus": [
                    "respect for religious practice",
                    "cultural-property protection",
                    "appropriate use of CIMIC and specialist advice"
                ]
            },
            "autonomous_system": {
                "type": "ISR drone",
                "role": "reconnaissance and threat classification",
                "limitations": [
                    "may confuse tools or ceremonial weapons with hostile weapons",
                    "cannot independently authorize an attack"
                ],
                "human_control": "human authorization required for any escalation"
            },
            "map": {
                "unit_id": "alpha",
                "initial_location_id": "command",
                "available_location_ids": [
                    "command",
                    "village",
                    "bridge"
                ]
            }
        }
    },

    "village_shield": {
        "title": "Exercise Village Shield",
        "content": {
            "environment": "defensive",
            "operational_area": "The fictional region of Norland Valley",
            "mission": (
                "Protect the village following reports that an armed group is "
                "moving toward the bridge."
            ),
            "commanders_intent": (
                "Prevent an attack on the population without turning uncertain "
                "intelligence into unnecessary military escalation."
            ),
            "objectives": [
                "protect the village",
                "observe and control the bridge",
                "verify the identity and intentions of the armed group",
                "preserve civilian access where possible"
            ],
            "known_facts": [
                "Several armed persons were detected near the bridge.",
                "Their affiliation and intentions are unknown.",
                "Civilian vehicles remain in the area.",
                "Communications with local authorities are intermittent."
            ],
            "constraints": [
                "uncertain intelligence",
                "civilian population present",
                "proportionality and precaution required",
                "no autonomous use of lethal force"
            ],
            "cultural_context": {
                "description": (
                    "The population includes several religious and ethnic "
                    "communities. Local representatives can assist with communication."
                ),
                "training_focus": [
                    "avoid stereotyping",
                    "verify cultural information",
                    "consult CIMIC or the chaplain when relevant"
                ]
            },
            "autonomous_system": {
                "type": "ground surveillance and classification system",
                "role": "detect movement and classify possible threats",
                "limitations": [
                    "classification confidence is degraded",
                    "civilian and armed movement patterns may overlap"
                ],
                "human_control": (
                    "the commander must review ambiguous classifications and "
                    "authorize operational responses"
                )
            },
            "map": {
                "unit_id": "alpha",
                "initial_location_id": "command",
                "available_location_ids": [
                    "command",
                    "village",
                    "bridge"
                ]
            }
        }
    }
}


@app.get("/health")
def health():
    return {
        "ok": True,
        "scenario_count": len(SCENARIOS)
    }


@app.get("/scenarios")
def list_scenarios():
    return {
        "scenario_ids": ["random"] + list(SCENARIOS.keys()),
        "scenarios": [
            {
                "scenario_id": scenario_id,
                "title": scenario["title"]
            }
            for scenario_id, scenario in SCENARIOS.items()
        ]
    }


@app.post("/load_scenario")
def load_scenario(req: Req):
    requested_id = req.scenario_id.strip().lower()

    if requested_id == "random":
        selected_id = secrets.choice(list(SCENARIOS.keys()))
    else:
        selected_id = requested_id

    scenario = SCENARIOS.get(selected_id)

    if scenario is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "unknown_scenario_id",
                "requested_id": requested_id,
                "available_ids": ["random"] + list(SCENARIOS.keys())
            }
        )

    return {
        "scenario_id": selected_id,
        "title": scenario["title"],
        "content": scenario["content"]
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
