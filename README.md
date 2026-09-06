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
