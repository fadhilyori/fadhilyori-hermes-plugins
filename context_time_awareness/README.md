# context_time_awareness

Injects current local time into LLM context on every turn, plus time elapsed since the last user message in the same session. Also provides lightweight event scheduling so the agent can remind the user about upcoming events.

**Hooks used:** `pre_llm_call`

**Tools provided:** `add_event`, `add_events`, `list_events`, `get_event`, `update_event`, `delete_event`, `mark_event_complete`

**Elapsed time format:** `1y 2M 14d 23h 14m`  
Components with zero value are omitted. For example, `2h 0m` becomes `2h`, and durations under one minute are shown as `just now`. Event duration formatting (used in the `end_time` output field) uses `<1m` for sub-minute durations, distinct from the `just now` used in the elapsed-time line.

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

The active window for context injection runs from `reminder_minutes_before` before the start time until `end_time` (or 30 minutes after the start time, whichever is later). The `reminder_minutes_before` value is configurable per event; the 30-minute post-start window is fixed. The default reminder is 5 minutes.

Example context:

```text
Current local time: 2024-06-15 14:30 WIB (Saturday, Asia/Jakarta)
Time since last user message: 5m
Upcoming:
- Meeting with client (in 15m)
- Standup until 15:00 (in 5m)
Now:
- Call with team (started just now)
```

### Tools

| Tool | Description |
| ------ | ------------- |
| `add_event` | Create a single event. |
| `add_events` | Create multiple events in one call. |
| `list_events` | List events. Use `filter=today` / `upcoming` / `past` for quick buckets, or `start_date` / `end_date` (`YYYY-MM-DD`) for a specific date or week. Returns events in the window `(now, now + 14d]` — events starting at exactly `now` are excluded. |
| `get_event` | Get a single event by ID. |
| `update_event` | Update an event. Only provided fields are changed. Set `end_time` to `null` to remove it. Set `completed_at` to `null` to unmark a completed event; use `mark_event_complete` to mark an event as complete. |
| `delete_event` | Delete an event by ID. |
| `mark_event_complete` | Mark an event as complete. Idempotent. To unmark, pass `completed_at: null` to `update_event`. |

`list_events` with `filter=upcoming` returns events scheduled within the next two weeks.

### Date-range queries

For questions about a specific date or a week, pass `start_date` and
`end_date` to `list_events` in `YYYY-MM-DD` format (local time).
When either is set, `filter` is ignored.

- `start_date` only — a single day.
- `start_date` + `end_date` — an inclusive range.
- `end_date` requires `start_date` and must be on or after it.
- An event that starts before the range and ends inside it is still
  returned (interval-overlap rule).
- Pass `show_completed: true` to also get completed events in the
  same range.

Event output now includes `duration_minutes`. It equals
`(end_time - start_time) / 60` when `end_time` is set; otherwise it
defaults to **60** as a best guess. Use it to compute free-time
windows or to find the busiest day.

### Time input

`start_time` and `end_time` accept ISO 8601 strings. You may include a timezone offset (e.g. `2024-06-15T14:30:00+07:00`) or omit it to use the local timezone configured in the environment.

### Cleanup

Events older than 30 days are removed once when the plugin starts. Long-term calendar tracking should remain in Google Calendar or another primary calendar integration.
