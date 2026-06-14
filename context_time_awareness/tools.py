"""Tool handlers for the scheduler toolset."""

import json

from . import store


def _ok(payload: dict) -> str:
    return json.dumps({"success": True, **payload})


def _err(message: str) -> str:
    return json.dumps({"error": message})


def add_event(args: dict, **kwargs) -> str:
    title = (args.get("title") or "").strip()
    start_time = (args.get("start_time") or "").strip()
    if not title:
        return _err("title is required")
    if not start_time:
        return _err("start_time is required")
    try:
        event = store.create_event(
            title=title,
            start_time=start_time,
            end_time=args.get("end_time"),
            description=args.get("description"),
            reminder_minutes_before=args.get("reminder_minutes_before", 5),
        )
        return _ok({"event": event})
    except (ValueError, RuntimeError) as e:
        return _err(str(e))


def add_events(args: dict, **kwargs) -> str:
    events = args.get("events", [])
    if not isinstance(events, list):
        return _err("events must be a list")
    if not events:
        return _err("events list is empty")

    for i, e in enumerate(events):
        if not isinstance(e, dict):
            return _err(f"event at index {i} must be an object")
        if not isinstance(e.get("title"), str) or not e["title"].strip():
            return _err(f"event at index {i} title must be a non-empty string")
        if not isinstance(e.get("start_time"), str) or not e["start_time"].strip():
            return _err(f"event at index {i} start_time must be a non-empty string")

    try:
        count = store.create_events(events)
        return _ok({"created_count": count})
    except (ValueError, RuntimeError) as e:
        return _err(str(e))


def list_events(args: dict, **kwargs) -> str:
    filter_value = args.get("filter", "upcoming")
    if filter_value not in {"upcoming", "past", "today"}:
        return _err("filter must be 'upcoming', 'past', or 'today'")
    try:
        limit = int(args.get("limit", 10))
    except (TypeError, ValueError):
        return _err("limit must be an integer")
    show_completed = bool(args.get("show_completed", False))

    try:
        events = store.fetch_events(filter=filter_value, limit=limit)
    except (ValueError, RuntimeError) as e:
        return _err(str(e))

    if show_completed:
        completed = store.fetch_completed_events(
            filter=filter_value, limit=limit)
        return json.dumps({"active": events, "completed": completed})
    return json.dumps({"events": events})


def get_event(args: dict, **kwargs) -> str:
    event_id = (args.get("event_id") or "").strip()
    if not event_id:
        return _err("event_id is required")
    try:
        event = store.fetch_event(event_id)
    except (ValueError, RuntimeError) as e:
        return _err(str(e))
    if event is None:
        return _err(f"Event '{event_id}' not found")
    return _ok({"event": event})


def update_event(args: dict, **kwargs) -> str:
    event_id = (args.get("event_id") or "").strip()
    if not event_id:
        return _err("event_id is required")

    fields = {
        k: args[k] for k in
        ("title", "description", "start_time", "end_time",
         "reminder_minutes_before", "completed_at")
        if k in args
    }
    if not fields:
        return _err("at least one field to update is required")

    try:
        event = store.modify_event(event_id, **fields)
    except (ValueError, RuntimeError) as e:
        return _err(str(e))
    if event is None:
        return _err(f"Event '{event_id}' not found")
    return _ok({"event": event})


def delete_event(args: dict, **kwargs) -> str:
    event_id = (args.get("event_id") or "").strip()
    if not event_id:
        return _err("event_id is required")
    try:
        if not store.remove_event(event_id):
            return _err(f"Event '{event_id}' not found")
    except (ValueError, RuntimeError) as e:
        return _err(str(e))
    return _ok({"deleted": True})


def mark_event_complete(args: dict, **kwargs) -> str:
    event_id = (args.get("event_id") or "").strip()
    if not event_id:
        return _err("event_id is required")
    try:
        event = store.mark_event_complete(event_id)
    except (ValueError, RuntimeError) as e:
        return _err(str(e))
    if event is None:
        return _err(f"Event '{event_id}' not found")
    return _ok({"event": event})
