# AI agent (Grok)

## Principles

1. **Grok never touches the database.** It can only call tools in the registry, and each tool calls a backend service.
2. **The backend matches and ranks.** Grok interprets the user's request and explains the results.
3. **Tools run as the requesting user.** Every call re-checks the user's role and validates the arguments.
4. **Consequential actions need the user's explicit confirmation** through a separate endpoint that Grok cannot reach.
5. **Everything is logged.** Each message is saved, and every tool call writes an `AIActionLog` row.
6. **The xAI API key stays on the server.** It is never returned, logged or put in an error message.

## Architecture

```
POST /api/v1/ai/chat/ ──► views.ChatView (throttle scope ai_chat, max 2000 chars)
                              │
                              ▼
                       agent.run_chat(user, message, conversation_id)
                              │  system prompt: role, name, town/municipality/province,
                              │  today's date and strict rules (no coordinates)
                              │  tools: registry.grok_tools_for_user(user)  (role-filtered)
                              ▼
                ┌──── client.create_response(...)  ◄──────────────┐
                │      (xAI Responses API, store=False)           │
                │                                                 │
       tool calls?  yes ──► registry.execute_tool_call(user, ...) │
                │             auth + role check                   │
                │             serializer validation               │
                │             requires_confirmation? ─► PendingAction (not executed)
                │             else run service as user            │
                │             scrub private fields                │
                │             AIActionLog row                     │
                │           feed results back ────────────────────┘  (max 5 rounds)
                no
                ▼
        reply + tool_calls + data + pending_action
```

| File | Role |
|---|---|
| `apps/ai/client.py` | Wrapper around the `openai` SDK at `XAI_BASE_URL`. One public function, `create_response()`, returns a provider-neutral `ModelTurn(text, tool_calls)`. Retries transient errors (timeouts, connection errors, 408/409/429/5xx) with exponential backoff, then raises `AIServiceUnavailable` (HTTP 503). |
| `apps/ai/agent.py` | System prompt and agent loop. |
| `apps/ai/tools/registry.py` | `register_tool`, role filtering, execution, logging and the confirm/cancel logic. |
| `apps/ai/tools/definitions.py` | The nine tools and their input serializers. |
| `apps/ai/tools/schema.py` | Builds JSON Schema from DRF serializers. |
| `apps/ai/tools/privacy.py` | Strips `email`, `phone_number`, `latitude`, `longitude`, `address_line` and similar keys from every result as a safety net. |
| `apps/ai/services_contract.py` | Service signatures, return shapes and provider paths for Members 2-4. |

### Why the Responses API

xAI's documentation recommends the Responses API for function calling and marks Chat Completions as legacy. We use it statelessly (`store=False`): every round re-sends the input items (`{"role": ..., "content": ...}`, `function_call` and `function_call_output`), so xAI doesn't need to keep our conversation. Our own database is the record. Everything else in the code uses `ModelTurn`, so switching APIs or providers only means changing `client.py`.

### Conversation history

Each chat request sends Grok the last `AI_HISTORY_MESSAGES` (20) **user and assistant text messages** of the conversation. Tool results from earlier turns are stored but not replayed. If Grok needs fresh data it calls the tool again, so the data is never stale.

### Limits

| Setting | Default | Meaning |
|---|---|---|
| `AI_MAX_TOOL_ROUNDS` | 5 | After 5 rounds of tool calls, Grok is called once more with **no tools** and must answer. If it still returns no text, a fallback reply is used. |
| `AI_MAX_MESSAGE_LENGTH` | 2000 | Longer user messages are rejected with 400. |
| `AI_PENDING_ACTION_TTL_MINUTES` | 15 | How long a proposed action can be confirmed. |
| `ai_chat` throttle | 20/min per user | |
| Tool output | 20,000 characters | Larger results are replaced with `result_too_large`. |

## The chat API

```http
POST /api/v1/ai/chat/
{"conversation_id": null, "message": "Find farmers near me"}
```

```json
{
  "conversation_id": "1f0c...",
  "reply": "The nearest farmers are Jozi Veg (same town) and Soweto Greens (≈ 21 km).",
  "tool_calls": [{"name": "find_nearby_farmers", "status": "success"}],
  "data": {
    "find_nearby_farmers": {
      "available": true,
      "count": 2,
      "results": [
        {"farmer_id": 4, "display_name": "Jozi Veg",
         "location": {"province": "GAUTENG", "province_display": "Gauteng",
                      "municipality": "City of Johannesburg", "town": "Johannesburg",
                      "distance": {"km": null, "basis": "same_town", "label": "Same town"}}}
      ]
    }
  },
  "pending_action": null
}
```

- `tool_calls[].status` is one of `success`, `denied`, `invalid`, `error` or `pending_confirmation`.
- `data` holds the **successful** results keyed by tool name, for the app to render as cards. If the same tool runs twice in one request, the last result wins. A stub returns `{"available": false, "reason": "..."}`.
- `pending_action` is set when Grok proposed a consequential action. If it proposed several in one request, only the last one is returned (all of them are stored).
- A Grok outage returns `503 {"error": {"code": "ai_service_unavailable", ...}}`. The user's message is still saved.

## Confirmation flow

1. Grok calls a tool with `requires_confirmation=True`, such as `create_or_update_listing`.
2. The registry checks the role, validates the arguments and creates a `PendingAction` with a plain-language summary, such as *"Create a listing: 500 kg potatoes at R8.00/kg, available from 20 Nov 2026"*. **Nothing runs.**
3. Grok receives `{"status": "confirmation_required", "summary": ..., "message": "Nothing has been done yet..."}`. It does not receive the action ID.
4. The app shows `pending_action.summary` with Confirm and Cancel buttons:
   - `POST /api/v1/ai/actions/{id}/confirm/` → `200 {"id", "status": "confirmed", "result": {...}}`
   - `POST /api/v1/ai/actions/{id}/cancel/` → `200 {"status": "cancelled"}`
5. On confirm, the server re-checks ownership and role, re-validates the stored arguments, claims the action atomically (`pending` → `executing`, so it can only run once), runs it, and logs `confirmed`.

| Situation | Response |
|---|---|
| Not the owner, or unknown ID | 404 `not_found` |
| Already confirmed or cancelled | 409 `action_not_pending` |
| Expired | 410 `action_expired`, and the action is marked expired |
| Role no longer allowed | 403 `permission_denied`, and the action is marked failed |
| Arguments no longer valid | 400 `validation_error`, and the action is marked failed |

If a confirmation tool's service isn't built yet, no `PendingAction` is created. The tool returns `available: false` straight away, so users never confirm something that can't happen.

There is no tool that confirms or cancels, and confirm/cancel are only reachable through the authenticated API. Grok has no way to confirm for the user.

## Audit log (`AIActionLog`)

The log is append-only, with one row per event: `success`, `denied`, `invalid`, `error`, `pending_confirmation`, `confirmed`, `cancelled` or `expired`. Each row stores the arguments Grok sent (truncated at 4 KB), a short result summary, and `executed_at` when something actually ran. You can browse it read-only in Django admin.

## Adding a new tool

1. **Define the service contract** in `apps/ai/services_contract.py`: a `Protocol` for the signature, a `TypedDict` for the result, and a `SERVICE_PROVIDERS` entry pointing at the module that will implement it.
2. **Write an input serializer and register the tool** in `apps/ai/tools/definitions.py`:

```python
class FindBuyersInput(serializers.Serializer):
    produce = produce_field()
    max_distance_km = max_distance_field()
    limit = limit_field()

@register_tool(
    name="find_buyers",                 # snake_case verb_noun
    description="For a farmer: ...",    # Grok reads this; say what it returns and any limits
    input_serializer=FindBuyersInput,   # becomes the JSON schema; validates Grok's arguments
    allowed_roles={FARMER},
    requires_confirmation=False,        # True for anything that creates, changes, commits or pays
    service="find_buyers",
)
def find_buyers(user, data):
    return call_service("find_buyers", user, data)
```

   For a confirmation tool, also pass `summarize=lambda data: "Plain-language description"`.
3. **Implement the service** in the module named in `SERVICE_PROVIDERS` (see `INTEGRATION_GUIDE.md`).
4. **Write tests** in the style of `apps/ai/tests/`: role filtering, invalid arguments, a success result that contains no private fields, and the confirmation flow if relevant.

The JSON-schema generator supports Char, Choice, Integer, Decimal, Float, Boolean, Date, DateTime, List and nested serializers. For anything else, pass `json_schema={...}` to `register_tool`.

Rules for tool results:

- Return compact, JSON-serialisable dicts. Use the envelope `{"available": true, "count": n, "results": [...]}` for searches.
- Include `match_reasons` and `shortfall` so Grok explains with facts instead of inventing them.
- Never include other users' contact details or coordinates.
- Raise `PermissionDenied` or `ValidationError` from the service when appropriate. The registry logs them and tells Grok.

## Testing

Tests never call xAI:

- Use the `fake_grok(*turns)` fixture (`apps/ai/tests/conftest.py`) to script Grok, for example `fake_grok(tool_turn("find_nearby_farmers", limit=3), text_turn("Here they are"))`. It records the prompt, input and tools of every call.
- The root `conftest.py` blocks building a real SDK client in every test.
- `apps/ai/tests/test_client.py` tests the wrapper against a fake SDK object (parsing, retries and secret handling).
