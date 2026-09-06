# major-plato-api
API és MCP kapcsolat major platoval


## Text simulation endpoint

POST /turn resolves one graphical-game turn through the OpenAI Responses API.

Required Render environment variable:

- OPENAI_API_KEY

Optional variables:

- OPENAI_MODEL (default: gpt-4.1-mini)
- MAP_API_URL (the tactical map Site base URL)
- MAP_API_KEY (the map API key; never commit it)

The caller should persist the returned response_id and send it as previous_response_id on the next turn. It must also persist the returned game state, event list, and map session ID. If a map session ID and map credentials are supplied, validated move_unit actions are dispatched to the map API; a map action is only reported as confirmed after a successful map API response.

Example request:

```json
{
  "session_id": "demo-001",
  "scenario_id": "random",
  "player_action": {
    "type": "move_unit",
    "unit_id": "alpha",
    "target_location_id": "bridge"
  },
  "game_state": {},
  "recent_events": [],
  "state_summary": "",
  "map_session_id": "map-session-id"
}
```

The API never stores secrets in the repository. Configure them in Render Environment Variables.


## Durable game sessions

POST /game_sessions creates a scenario-backed game session through the tactical map API. The map's D1 database stores the map state and event log; the state also contains the text engine's turn counter, summary, response ID, conversation ID, and last adjudicated turn.

GET /game_sessions/{session_id} reads the durable state and event log. Supply the returned map session token as the x-session-token header or token query parameter.

POST /turn resolves one graphical-game turn. In durable mode send:

- session_id and map_session_id: the map session ID
- map_session_token: the session token returned by /game_sessions
- scenario_id: random on the first request, or the session's resolved ID
- player_action: the player's proposed action
- optional expected_turn and turn_id for conflict detection and retry-safe idempotency

The server retrieves the persisted state and recent events, uses the stored previous response ID when present, calls the OpenAI Responses API with structured JSON output, validates map actions, queues only supported actions, and persists the adjudication result back to the map event log. A 201 map response is reported as queued, not as unit arrival; the frontend confirms arrival through the map event.

Required Render environment variables:

- OPENAI_API_KEY
- MAP_API_URL=https://major-plato-tactical-map.milanmor.chatgpt.site
- MAP_API_KEY

Optional variables:

- OPENAI_MODEL (default: gpt-4.1-mini)
- MAP_FRONTEND_ORIGIN (default: https://major-plato-tactical-map.milanmor.chatgpt.site)
- TURN_CLIENT_KEY (required only for stateless /turn calls without a map session)

Example session creation:

```json
POST /game_sessions
{"scenario_id":"random"}
```

Example turn:

```json
{
  "session_id": "map-session-id",
  "map_session_id": "map-session-id",
  "map_session_token": "returned-session-token",
  "scenario_id": "random",
  "player_action": {
    "type": "move_unit",
    "payload": {
      "unit_id": "alpha",
      "target_location_id": "bridge"
    }
  },
  "expected_turn": 1,
  "turn_id": "client-generated-id"
}
```

Do not put OPENAI_API_KEY, MAP_API_KEY, or GitHub tokens in source control or browser code.
