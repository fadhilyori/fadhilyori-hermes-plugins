# context_time_awareness

Injects current local time into LLM context on every turn, plus time elapsed since the last user message in the same session. Also provides lightweight event scheduling so the agent can remind the user about upcoming events.

**Hooks used:** `pre_llm_call`, `on_session_start`

**Tools provided:** `add_event`, `add_events`, `list_events`, `get_event`, `update_event`, `delete_event`

**Elapsed time format:** `1y 2M 14d 23h 14m`  
Components with zero value are omitted. For example, `2h 0m` becomes `2h`, and durations under one minute are shown as `just now`.

**Dependency:**

```bash
pip install -r requirements.txt
```

Timestamps are persisted to SQLite so the agent remains aware of session gaps across gateway restarts.

## Event scheduling

The agent can create, list, update, and delete events. Events are stored in the same SQLite database as the session timestamps. All times are stored as UTC internally and displayed in local time.

### Context injection

When an event is within its reminder window, the hook injects it into the context under one of two sections:

- **Upcoming** — the event has not started yet.
- **Now** — the event is currently happening or has just started.

The active window for context injection runs from `reminder_minutes_before` before the start time until 30 minutes after the start time. The `reminder_minutes_before` value is configurable per event; the 30-minute post-start window is fixed. The default reminder is 5 minutes.

Example context:

```text
Current local time: 2024-06-15 14:30 WIB (Saturday, Asia/Jakarta)
Time since last user message: 5m
Upcoming:
- Meeting with client (in 15m)
Now:
- Call with team (started just now)
```

### Tools

| Tool | Description |
|------|-------------|
| `add_event` | Create a single event. |
| `add_events` | Create multiple events in one call. |
| `list_events` | List events filtered by `upcoming`, `past`, or `today`. |
| `get_event` | Get a single event by ID. |
| `update_event` | Update an event. Only provided fields are changed. Set `end_time` to `null` to remove it. |
| `delete_event` | Delete an event by ID. |

`list_events` with `filter=upcoming` returns events scheduled within the next two weeks.

### Time input

`start_time` and `end_time` accept ISO 8601 strings. You may include a timezone offset (e.g. `2024-06-15T14:30:00+07:00`) or omit it to use the local timezone configured in the environment.

### Cleanup

Events older than 30 days are automatically removed during `pre_llm_call`, throttled to once per hour. This keeps the local reminder store lightweight; long-term calendar tracking should remain in Google Calendar or another primary calendar integration.
