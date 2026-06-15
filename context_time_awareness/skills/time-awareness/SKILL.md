---
name: time-awareness
description: |
  Provides time-awareness and event scheduling. Injects the current
  local time, time since the last user message, and any active or
  upcoming scheduled events into the agent's context. Exposes tools
  to create, list, update, delete, and complete events. Use when
  the user mentions schedules, meetings, appointments, reminders,
  deadlines, agendas, or asks about the current time or upcoming
  activities.
license: MIT
metadata:
  author: fadhilyori
  version: 1.2.0
---

# Time Awareness

## What this plugin provides

- **Context injection** — On every LLM turn, the `pre_llm_call` hook
  appends a block to the system context containing:
  - Current local time (with timezone)
  - Time elapsed since the last user message in this session
  - `Upcoming:` — events whose start time is approaching
  - `Now:` — events that are currently in their active window

- **Scheduling tools** — Create, read, update, delete, and complete
  scheduled events. Events are stored in SQLite (UTC internally,
  displayed in local time).

## Tools

| Tool | Purpose |
|------|---------|
| `add_event` | Create a single event. |
| `add_events` | Create multiple events. |
| `list_events` | List events. Use `filter=today` / `upcoming` / `past` for quick buckets, or `start_date` / `end_date` (format `YYYY-MM-DD`) for a specific date or week. |
| `get_event` | Fetch a single event by ID. |
| `update_event` | Change fields on an existing event. |
| `delete_event` | Remove an event. |
| `mark_event_complete` | Mark an event as done. Idempotent. |

## Event output

Every event returned by the tools includes:

- `event_id`, `title`, `description`
- `start_time` (formatted string with timezone and a relative hint)
- `end_time` (only present when explicitly set at creation)
- `duration_minutes` — always present. Equals `(end_time - start_time) / 60`
  when `end_time` is set; otherwise defaults to **60** as a best guess.
  Treat the default as an estimate, not a guarantee.
- `reminder_minutes_before`
- `completed` and `completed_at`
- `notify` — always `false`. Kept for backward compatibility with older
  agents; the plugin no longer has a separate notify concept.

## Context injection

The injected block looks like:

```text
Current local time: 2024-06-15 14:30 WIB (Saturday, Asia/Jakarta)
Time since last user message: 5m
Upcoming:
- Meeting with client (in 15m)
Now:
- Call with team (started just now)
```

The `Upcoming` section is populated from
`reminder_minutes_before` minutes before the event start until the
event's active window begins. The `Now` section covers the event's
active window: until `end_time`, or 30 minutes after the start time
if `end_time` is not set.

## Date-range queries

For questions about a specific date or a week, pass `start_date` and
`end_date` to `list_events` in `YYYY-MM-DD` format (local time).
When either is set, `filter` is ignored.

- `start_date` only — a single day.
- `start_date` + `end_date` — an inclusive range.
- `end_date` requires `start_date`.
- `end_date` must be on or after `start_date`.
- An event that starts before the range and ends inside it is still
  returned (interval-overlap rule).
- Pass `show_completed: true` to also get completed events in the
  same range.

Common patterns:

- "What time am I free tomorrow?" → `list_events(start_date=tomorrow)`
- "Am I free on the 15th?" → `list_events(start_date="2026-06-15")`
- "What day this week am I free all day?" → `list_events(start_date=monday, end_date=sunday)`, then group by day
- "What day this week is busiest?" → same call, then sum `duration_minutes` per day

Use `duration_minutes` to compute free-time windows or to find the
busiest day.

## State transitions

| Intent | Tool |
|--------|------|
| Change time, title, or details | `update_event` |
| Remove an event | `delete_event` |
| Mark an event as done | `mark_event_complete` |
| Unmark a completed event | `update_event` with `completed_at: null` |

## Time input

`start_time` and `end_time` accept ISO 8601 strings. Times without a
timezone offset are interpreted in the local timezone (from `TZ`
env or system). Include an explicit offset (e.g. `+07:00`) when
ambiguity is possible.

## Edge cases

- Recurring events are NOT supported. The plugin does not repeat
  events. For recurrence, create individual events or use a primary
  calendar.
- Events older than 30 days are removed when the plugin starts.
- `completed_at` cannot be set to a non-null value via
  `update_event` — use `mark_event_complete` instead. Pass
  `completed_at: null` to `update_event` to unmark a completed
  event.
- `list_events` with `filter=upcoming` returns events scheduled
  within the next two weeks.
- `duration_minutes` defaults to 60 when `end_time` was not set at
  creation — treat it as an estimate, not a guarantee.
- `list_events` with `start_date` / `end_date` returns events that
  overlap the range, not events that start inside it. An event
  starting the day before and ending the day after is included.
- Respect explicit TZ offsets in ISO strings (e.g. `+07:00`).
- Use `add_events` for bulk, not loops of `add_event`.
