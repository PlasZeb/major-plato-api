from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from typing import Any, Dict, List, Optional, Union
import os, json, base64, uuid, secrets
import requests

app = FastAPI()

_FRONTEND_ORIGIN = os.environ.get(
    "MAP_FRONTEND_ORIGIN",
    "https://major-plato-tactical-map.milanmor.chatgpt.site"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_FRONTEND_ORIGIN],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

# --- Durable game-session and text simulation endpoints ---
class CreateGameSessionRequest(BaseModel):
    scenario_id: str = "random"
    title: Optional[str] = None


class TurnRequest(BaseModel):
    session_id: str
    scenario_id: str = "random"
    player_action: Dict[str, Any]
    game_state: Dict[str, Any] = Field(default_factory=dict)
    recent_events: List[Dict[str, Any]] = Field(default_factory=list)
    state_summary: str = ""
    previous_response_id: Optional[str] = None
    conversation_id: Optional[str] = None
    map_session_id: Optional[str] = None
    map_session_token: Optional[str] = None
    turn_id: Optional[str] = None
    expected_turn: Optional[int] = None


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
state, recent events, state summary, and player action.

Apply MDMP reasoning and explicitly account for mission, objectives, constraints, civilian
protection, proportionality, precaution, positive identification, cultural context, and
human authorization. Autonomous systems can observe or classify, but cannot independently
authorize escalation or lethal force. Do not invent capabilities or map identifiers.

Return only the requested JSON schema. map_actions are proposed game actions, not proof that
the action happened. Only use the supported map unit alpha and locations command, village,
or bridge. If the action is unsafe, unauthorized, or unsupported, do not emit a map action;
explain the consequence in narrative and assessment. Never claim that a unit has arrived
until the map service produces the corresponding event.
"""


def _resolve_scenario(requested_id: str):
    normalized = (requested_id or "random").strip().lower()
    selected_id = secrets.choice(list(SCENARIOS.keys())) if normalized == "random" else normalized
    scenario = SCENARIOS.get(selected_id)
    if scenario is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "unknown_scenario_id",
                "requested_id": normalized,
                "available_ids": ["random"] + list(SCENARIOS.keys())
            }
        )
    return selected_id, scenario


def _map_settings():
    base_url = os.environ.get("MAP_API_URL", "").rstrip("/")
    api_key = os.environ.get("MAP_API_KEY")
    if not base_url or not api_key:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "map_api_not_configured",
                "required": ["MAP_API_URL", "MAP_API_KEY"]
            }
        )
    return base_url, api_key


def _map_request(
    method: str,
    path: str,
    body: Optional[Dict[str, Any]] = None,
    session_token: Optional[str] = None,
    privileged: bool = True,
):
    base_url, api_key = _map_settings()
    headers = {"Content-Type": "application/json"}
    if privileged:
        headers["X-Major-Plato-Key"] = api_key
    elif session_token:
        headers["X-Session-Token"] = session_token
    try:
        return requests.request(
            method,
            f"{base_url}{path}",
            headers=headers,
            json=body,
            timeout=30,
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": "map_api_unreachable", "message": str(exc)}
        )


def _response_json(response):
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text[:1000]}


def _raise_map_error(response, operation: str):
    if response.status_code < 400:
        return
    if response.status_code in (401, 403, 404):
        raise HTTPException(
            status_code=response.status_code,
            detail={
                "error": "map_api_error",
                "operation": operation,
                "response": _response_json(response)
            }
        )
    raise HTTPException(
        status_code=502,
        detail={
            "error": "map_api_error",
            "operation": operation,
            "http_status": response.status_code,
            "response": _response_json(response)
        }
    )


def _map_session_state(session_id: str, session_token: Optional[str]):
    if not session_token:
        raise HTTPException(
            status_code=401,
            detail="A map session token szükséges a játékmenethez."
        )
    response = _map_request(
        "GET",
        f"/api/major-plato/sessions/{session_id}/state",
        session_token=session_token,
        privileged=False,
    )
    _raise_map_error(response, "get_session_state")
    return _response_json(response)


def _map_session_events(session_id: str):
    response = _map_request(
        "GET",
        f"/api/major-plato/sessions/{session_id}/events",
        privileged=True,
    )
    _raise_map_error(response, "get_session_events")
    payload = _response_json(response)
    return payload.get("events", [])


def _default_game_state(scenario_id: str):
    return {
        "schema_version": "2.0",
        "turn": 1,
        "units": {
            "alpha": {
                "label": "Alpha raj",
                "side": "friendly",
                "status": "ready",
                "location_id": "command",
                "position": {"x": 170, "y": 395}
            }
        },
        "last_event": None,
        "engine": {
            "scenario_id": scenario_id,
            "summary": "A szcenárió betöltve; a parancsnoki döntésre vár.",
            "response_id": None,
            "conversation_id": None,
            "last_turn_id": None,
            "last_response": None,
            "state_delta": None,
            "updated_at": None
        }
    }


def _engine_state(game_state: Dict[str, Any], scenario_id: str):
    engine = game_state.get("engine")
    if not isinstance(engine, dict):
        engine = {}
        game_state["engine"] = engine
    engine.setdefault("scenario_id", scenario_id)
    engine.setdefault("summary", "")
    engine.setdefault("response_id", None)
    engine.setdefault("conversation_id", None)
    engine.setdefault("last_turn_id", None)
    engine.setdefault("last_response", None)
    engine.setdefault("state_delta", None)
    engine.setdefault("updated_at", None)
    return engine


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
        raise HTTPException(
            status_code=502,
            detail={"error": "openai_empty_output", "response": response_body}
        )
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": "invalid_model_json", "message": str(exc)}
        )


def _dispatch_map_actions(map_session_id, actions):
    if not actions:
        return {"status": "not_requested", "results": []}
    results = []
    for action in actions:
        response = _map_request(
            "POST",
            f"/api/major-plato/sessions/{map_session_id}/actions",
            body=action,
            privileged=True,
        )
        if 200 <= response.status_code < 300:
            action_status = "queued" if response.status_code == 201 else "confirmed"
            results.append({
                "action": action,
                "status": action_status,
                "response": _response_json(response)
            })
        else:
            results.append({
                "action": action,
                "status": "rejected",
                "http_status": response.status_code,
                "response": _response_json(response)
            })
    if any(item["status"] == "rejected" for item in results):
        overall = "partially_rejected"
    elif any(item["status"] == "queued" for item in results):
        overall = "queued"
    else:
        overall = "confirmed"
    return {"status": overall, "results": results}


def _persist_turn_to_map(
    map_session_id: str,
    current_state: Dict[str, Any],
    turn_id: str,
    response_id: Optional[str],
    conversation_id: Optional[str],
    model_turn: Dict[str, Any],
    validated_actions: List[Dict[str, Any]],
    rejected_actions: List[Dict[str, Any]],
    dispatch: Dict[str, Any],
):
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    next_state = json.loads(json.dumps(current_state))
    next_state["schema_version"] = "2.0"
    next_state["turn"] = int(next_state.get("turn", 1)) + 1
    engine = _engine_state(next_state, current_state.get("engine", {}).get("scenario_id", ""))
    response_record = {
        "response_id": response_id,
        "conversation_id": conversation_id,
        "turn": model_turn,
        "map_actions": {
            "validated": validated_actions,
            "rejected": rejected_actions,
            "dispatch": dispatch
        }
    }
    engine.update({
        "summary": model_turn.get("next_state_summary", ""),
        "response_id": response_id,
        "conversation_id": conversation_id,
        "last_turn_id": turn_id,
        "last_response": response_record,
        "state_delta": model_turn.get("state_delta"),
        "updated_at": now
    })
    next_state["last_event"] = {
        "type": "ai_turn_resolved",
        "turn_id": turn_id,
        "occurred_at": now
    }
    event_payload = {
        "source": "text_engine",
        "turn_id": turn_id,
        "response_id": response_id,
        "conversation_id": conversation_id,
        "narrative": model_turn.get("narrative", ""),
        "assessment": model_turn.get("assessment", {}),
        "state_delta": model_turn.get("state_delta", {}),
        "events": model_turn.get("events", []),
        "map_actions": response_record["map_actions"],
        "occurred_at": now
    }
    response = _map_request(
        "POST",
        f"/api/major-plato/sessions/{map_session_id}/events",
        body={
            "type": "ai_turn_resolved",
            "payload": event_payload,
            "state": next_state
        },
        privileged=True,
    )
    _raise_map_error(response, "persist_turn")
    return next_state, _response_json(response)


def _openai_response(
    context: Dict[str, Any],
    previous_response_id: Optional[str],
    conversation_id: Optional[str],
):
    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        raise HTTPException(status_code=503, detail="OpenAI API is not configured")
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
    if previous_response_id:
        payload["previous_response_id"] = previous_response_id
    elif conversation_id:
        payload["conversation"] = conversation_id

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
        raise HTTPException(
            status_code=502,
            detail={"error": "openai_request_failed", "message": str(exc)}
        )

    response_body = _response_json(response)
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "openai_api_error",
                "http_status": response.status_code,
                "response": response_body
            }
        )
    return response_body, _extract_openai_json(response_body)


@app.post("/game_sessions")
def create_game_session(req: CreateGameSessionRequest):
    selected_id, scenario = _resolve_scenario(req.scenario_id)
    initial_state = _default_game_state(selected_id)
    title = req.title.strip() if req.title else scenario["title"]
    response = _map_request(
        "POST",
        "/api/major-plato/sessions",
        body={
            "scenario_id": selected_id,
            "title": title,
            "initial_state": initial_state
        },
        privileged=True,
    )
    _raise_map_error(response, "create_session")
    created = _response_json(response)
    return {
        "session_id": created.get("session_id"),
        "map_session_id": created.get("session_id"),
        "session_token": created.get("session_token"),
        "map_url": created.get("map_url"),
        "created_at": created.get("created_at"),
        "scenario_id": selected_id,
        "title": title,
        "scenario": scenario["content"],
        "state": initial_state
    }


@app.get("/game_sessions/{session_id}")
def get_game_session(session_id: str, request: Request):
    token = request.headers.get("x-session-token") or request.query_params.get("token")
    snapshot = _map_session_state(session_id, token)
    events = _map_session_events(session_id)
    return {**snapshot, "events": events[-100:]}


@app.post("/turn")
def resolve_turn(turn: TurnRequest):
    if turn.previous_response_id and turn.conversation_id:
        raise HTTPException(
            status_code=400,
            detail="Use either previous_response_id or conversation_id, not both"
        )

    map_session_id = turn.map_session_id
    persisted_snapshot = None
    persisted_state = None
    persisted_events = []
    if map_session_id:
        persisted_snapshot = _map_session_state(map_session_id, turn.map_session_token)
        persisted_state = persisted_snapshot.get("state")
        if not isinstance(persisted_state, dict):
            raise HTTPException(status_code=502, detail="A map session állapota érvénytelen.")
        persisted_events = _map_session_events(map_session_id)

    if persisted_snapshot:
        stored_scenario_id = persisted_snapshot.get("scenario_id")
        requested_scenario_id = turn.scenario_id.strip().lower()
        if requested_scenario_id == "random":
            selected_id = stored_scenario_id
        elif stored_scenario_id and requested_scenario_id != stored_scenario_id:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "scenario_mismatch",
                    "session_scenario_id": stored_scenario_id,
                    "requested_scenario_id": requested_scenario_id
                }
            )
        else:
            selected_id = requested_scenario_id
        scenario = SCENARIOS.get(selected_id)
        if scenario is None:
            raise HTTPException(status_code=502, detail="A map session ismeretlen scenariót tartalmaz.")
    else:
        selected_id, scenario = _resolve_scenario(turn.scenario_id)

    if persisted_state is None:
        persisted_state = json.loads(json.dumps(turn.game_state or _default_game_state(selected_id)))
    engine = _engine_state(persisted_state, selected_id)
    if turn.expected_turn is not None and int(persisted_state.get("turn", 1)) != turn.expected_turn:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "turn_conflict",
                "expected_turn": turn.expected_turn,
                "current_turn": persisted_state.get("turn", 1)
            }
        )

    if turn.turn_id and engine.get("last_turn_id") == turn.turn_id and engine.get("last_response"):
        return {
            "session_id": turn.session_id,
            "scenario_id": selected_id,
            "idempotent_replay": True,
            **engine["last_response"]
        }

    previous_response_id = turn.previous_response_id or engine.get("response_id")
    conversation_id = turn.conversation_id or engine.get("conversation_id")
    if previous_response_id and conversation_id:
        conversation_id = None

    context = {
        "session_id": turn.session_id,
        "scenario_id": selected_id,
        "scenario": scenario,
        "player_action": turn.player_action,
        "game_state": persisted_state,
        "recent_events": (persisted_events[-20:] if persisted_snapshot else turn.recent_events[-20:]),
        "state_summary": engine.get("summary") or turn.state_summary
    }
    response_body, model_turn = _openai_response(
        context,
        previous_response_id,
        conversation_id,
    )
    validated_actions, rejected_actions = _validate_map_actions(
        model_turn.get("map_actions", [])
    )
    if map_session_id:
        dispatch = _dispatch_map_actions(map_session_id, validated_actions)
        actual_turn_id = turn.turn_id or str(uuid.uuid4())
        next_state, persisted_event = _persist_turn_to_map(
            map_session_id=map_session_id,
            current_state=persisted_state,
            turn_id=actual_turn_id,
            response_id=response_body.get("id"),
            conversation_id=(
                (response_body.get("conversation") or {}).get("id")
                if isinstance(response_body.get("conversation"), dict)
                else conversation_id
            ),
            model_turn=model_turn,
            validated_actions=validated_actions,
            rejected_actions=rejected_actions,
            dispatch=dispatch,
        )
    else:
        dispatch = {"status": "not_dispatched", "reason": "no_map_session", "results": []}
        actual_turn_id = turn.turn_id or str(uuid.uuid4())
        next_state = persisted_state
        persisted_event = None

    response_record = {
        "response_id": response_body.get("id"),
        "previous_response_id": response_body.get("id"),
        "conversation_id": (
            (response_body.get("conversation") or {}).get("id")
            if isinstance(response_body.get("conversation"), dict)
            else conversation_id
        ),
        "turn": model_turn,
        "map_actions": {
            "validated": validated_actions,
            "rejected": rejected_actions,
            "dispatch": dispatch
        }
    }
    return {
        "session_id": turn.session_id,
        "scenario_id": selected_id,
        "turn_id": actual_turn_id,
        "state": next_state,
        "persisted_event": persisted_event,
        **response_record
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
