from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional, Union
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

# --- Text simulation turn endpoint ---
class TurnRequest(BaseModel):
    session_id: str
    scenario_id: str
    player_action: Dict[str, Any]
    game_state: Dict[str, Any] = Field(default_factory=dict)
    recent_events: List[Dict[str, Any]] = Field(default_factory=list)
    state_summary: str = ""
    previous_response_id: Optional[str] = None
    conversation_id: Optional[str] = None
    map_session_id: Optional[str] = None


TURN_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "narrative": {"type": "string"},
        "assessment": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "ethical": {"type": "string"},
                "military": {"type": "string"},
                "command": {"type": "string"}
            },
            "required": ["ethical", "military", "command"]
        },
        "map_actions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "type": {"type": "string", "enum": ["move_unit"]},
                    "payload": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "unit_id": {"type": "string", "enum": ["alpha"]},
                            "target_location_id": {
                                "type": "string",
                                "enum": ["command", "village", "bridge"]
                            }
                        },
                        "required": ["unit_id", "target_location_id"]
                    }
                },
                "required": ["type", "payload"]
            }
        },
        "state_delta": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "summary": {"type": "string"},
                "unit_location_id": {
                    "type": "string",
                    "enum": ["command", "village", "bridge"]
                },
                "civilian_risk": {"type": "string"},
                "threat_assessment": {"type": "string"}
            },
            "required": [
                "summary",
                "unit_location_id",
                "civilian_risk",
                "threat_assessment"
            ]
        },
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "type": {"type": "string"},
                    "description": {"type": "string"}
                },
                "required": ["type", "description"]
            }
        },
        "next_state_summary": {"type": "string"}
    },
    "required": [
        "narrative",
        "assessment",
        "map_actions",
        "state_delta",
        "events",
        "next_state_summary"
    ]
}


TURN_INSTRUCTIONS = """
You are the authoritative text adjudicator for the Major Plato MDMP and military-ethics
training simulation. Resolve one player turn using the supplied scenario, current game
state, recent events, and player action.

Apply MDMP reasoning and explicitly account for mission, objectives, constraints, civilian
protection, proportionality, precaution, positive identification, cultural context, and
human authorization. Autonomous systems can observe or classify, but cannot independently
authorize escalation or lethal force. Do not invent capabilities or map identifiers.

Return only the requested JSON schema. map_actions are proposed game actions, not proof that
the action happened. Only use the supported map unit alpha and locations command, village,
or bridge. If the action is unsafe, unauthorized, or unsupported, do not emit a map action;
explain the consequence in narrative and assessment.
"""


def _validate_map_actions(actions):
    validated = []
    rejected = []
    for action in actions or []:
        if not isinstance(action, dict) or action.get("type") != "move_unit":
            rejected.append({"action": action, "reason": "unsupported_action"})
            continue
        payload = action.get("payload") or {}
        if payload.get("unit_id") != "alpha":
            rejected.append({"action": action, "reason": "unsupported_unit_id"})
            continue
        if payload.get("target_location_id") not in {"command", "village", "bridge"}:
            rejected.append({"action": action, "reason": "unsupported_location_id"})
            continue
        validated.append({
            "type": "move_unit",
            "payload": {
                "unit_id": "alpha",
                "target_location_id": payload["target_location_id"]
            }
        })
    return validated, rejected


def _extract_openai_json(response_body):
    text = response_body.get("output_text")
    if not text:
        chunks = []
        for item in response_body.get("output", []):
            for part in item.get("content", []) or []:
                if part.get("type") in {"output_text", "text"} and part.get("text"):
                    chunks.append(part["text"])
        text = "".join(chunks)
    if not text:
        raise HTTPException(status_code=502, detail="OpenAI returned no text output")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": "invalid_model_json", "message": str(exc)}
        )


def _dispatch_map_actions(map_session_id, actions):
    map_api_url = os.environ.get("MAP_API_URL", "").rstrip("/")
    map_api_key = os.environ.get("MAP_API_KEY")
    if not map_session_id:
        return {"status": "not_dispatched", "reason": "missing_map_session_id"}
    if not map_api_url or not map_api_key:
        return {"status": "not_dispatched", "reason": "map_api_not_configured"}

    results = []
    url = f"{map_api_url}/api/major-plato/sessions/{map_session_id}/actions"
    headers = {
        "X-Major-Plato-Key": map_api_key,
        "Content-Type": "application/json"
    }
    for action in actions:
        try:
            response = requests.post(url, headers=headers, json=action, timeout=20)
            if 200 <= response.status_code < 300:
                results.append({
                    "action": action,
                    "status": "confirmed",
                    "response": response.json()
                })
            else:
                results.append({
                    "action": action,
                    "status": "rejected",
                    "http_status": response.status_code,
                    "response": response.text[:500]
                })
        except requests.RequestException as exc:
            results.append({
                "action": action,
                "status": "error",
                "error": str(exc)
            })
    return {"status": "completed", "results": results}


@app.post("/turn")
def resolve_turn(turn: TurnRequest):
    if turn.previous_response_id and turn.conversation_id:
        raise HTTPException(
            status_code=400,
            detail="Use either previous_response_id or conversation_id, not both"
        )

    requested_id = turn.scenario_id.strip().lower()
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

    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        raise HTTPException(status_code=503, detail="OpenAI API is not configured")

    context = {
        "session_id": turn.session_id,
        "scenario_id": selected_id,
        "scenario": scenario,
        "player_action": turn.player_action,
        "game_state": turn.game_state,
        "recent_events": turn.recent_events[-20:],
        "state_summary": turn.state_summary
    }
    payload = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
        "instructions": TURN_INSTRUCTIONS,
        "input": json.dumps(context, ensure_ascii=False),
        "store": True,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "major_plato_turn",
                "strict": True,
                "schema": TURN_RESPONSE_SCHEMA
            }
        }
    }
    if turn.previous_response_id:
        payload["previous_response_id"] = turn.previous_response_id
    elif turn.conversation_id:
        payload["conversation"] = turn.conversation_id

    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {openai_key}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=90
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail={"error": "openai_request_failed", "message": str(exc)})

    response_body = response.json()
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "openai_api_error",
                "http_status": response.status_code,
                "response": response_body
            }
        )

    model_turn = _extract_openai_json(response_body)
    validated_actions, rejected_actions = _validate_map_actions(
        model_turn.get("map_actions", [])
    )
    dispatch = _dispatch_map_actions(turn.map_session_id, validated_actions)

    return {
        "session_id": turn.session_id,
        "scenario_id": selected_id,
        "response_id": response_body.get("id"),
        "previous_response_id": response_body.get("id"),
        "conversation_id": (
            (response_body.get("conversation") or {}).get("id")
            if isinstance(response_body.get("conversation"), dict)
            else turn.conversation_id
        ),
        "turn": model_turn,
        "map_actions": {
            "validated": validated_actions,
            "rejected": rejected_actions,
            "dispatch": dispatch
        }
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
