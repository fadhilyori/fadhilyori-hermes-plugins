"""Tool handlers for the scheduler toolset."""

import json
import logging

from . import store

logger = logging.getLogger(__name__)


def _json_error(message: str) -> str:
    """
    Helper function to return a JSON error message.

    Args:
        message (str): The error message to return.

    Returns:
        str: JSON string indicating the error.
    """
    return json.dumps({"error": message})


def add_event(args: dict, **kwargs) -> str:
    """
    Create a single event.

    Args:
        args (dict): A dictionary of arguments.
            * title (str): Event title.
            * start_time (str): Event start time in ISO 8601 format.
            * end_time (str, optional): Event end time in ISO 8601 format.
            * description (str, optional): Event description.
            * reminder_minutes_before (int, optional): Minutes before the event to start reminding.
        kwargs: Additional keyword arguments.

    Returns:
        str: JSON string indicating success or error.
    """
    title = args.get("title", "").strip()
    start_time = args.get("start_time", "").strip()
    if not title:
        return _json_error("title is required")
    if not start_time:
        return _json_error("start_time is required")

    try:
        event = store.create_event(
            title=title,
            start_time=start_time,
            end_time=args.get("end_time"),
            description=args.get("description"),
            reminder_minutes_before=args.get("reminder_minutes_before", 5),
        )
        return json.dumps({"success": True, "event": event})
    except ValueError as e:
        return _json_error(str(e))
    except Exception as e:
        logger.exception("tool handler failed")
        return _json_error(str(e))


def add_events(args: dict, **kwargs) -> str:
    """
    Add multiple events to the store.

    Args:
        args (dict): A dictionary of arguments.
            * events (list): A list of events to add.
        kwargs: Additional keyword arguments.

    Returns:
        str: JSON string indicating success or error.
    """
    events = args.get("events", [])
    if not isinstance(events, list):
        return _json_error("events must be a list")
    if not events:
        return _json_error("events list is empty")

    for i, e in enumerate(events):
        if not isinstance(e, dict):
            return _json_error(f"event at index {i} must be an object")
        title = str(e.get("title", "")).strip()
        start_time = str(e.get("start_time", "")).strip()
        if not title:
            return _json_error(f"event at index {i} is missing title")
        if not isinstance(e.get("title"), str):
            return _json_error(f"event at index {i} title must be a string")
        if not start_time:
            return _json_error(f"event at index {i} is missing start_time")
        if not isinstance(e.get("start_time"), str):
            return _json_error(f"event at index {i} start_time must be a string")

    try:
        count = store.create_events(events)
        return json.dumps({"success": True, "created_count": count})
    except ValueError as e:
        return _json_error(str(e))
    except Exception as e:
        logger.exception("tool handler failed")
        return _json_error(str(e))


def list_events(args: dict, **kwargs) -> str:
    """
    List events from the store.

    Args:
        args (dict): A dictionary of arguments.
            * filter (str, optional): Filter to apply to the events. Defaults to 'upcoming'.
            * limit (int, optional): Maximum number of events to return. Defaults to 10.
            * show_completed (bool, optional): When true, include a separate
                'completed' section listing events marked as complete. Defaults to False.
        kwargs: Additional keyword arguments.

    Returns:
        str: JSON string indicating success or error.
    """
    filter_value = args.get("filter", "upcoming")
    if filter_value not in {"upcoming", "past", "today"}:
        return _json_error("filter must be 'upcoming', 'past', or 'today'")
    limit = args.get("limit", 10)
    try:
        limit = int(limit) if limit is not None else 10
    except (TypeError, ValueError):
        return _json_error("limit must be an integer")

    show_completed = bool(args.get("show_completed", False))

    try:
        events = store.fetch_events(filter=filter_value, limit=limit)
        if show_completed:
            completed = store.fetch_completed_events(limit=limit)
            return json.dumps({"active": events, "completed": completed})
        return json.dumps({"events": events})
    except ValueError as e:
        return _json_error(str(e))
    except Exception as e:
        logger.exception("tool handler failed")
        return _json_error(str(e))


def get_event(args: dict, **kwargs) -> str:
    """
    Get a specific event by its ID.

    Args:
        args (dict): A dictionary of arguments.
            * event_id (str): The ID of the event to retrieve.
        kwargs: Additional keyword arguments.

    Returns:
        str: JSON string indicating success or error.
    """
    event_id = args.get("event_id", "").strip()
    if not event_id:
        return _json_error("event_id is required")

    try:
        event = store.fetch_event(event_id)
        if event is None:
            return _json_error(f"Event '{event_id}' not found")
        return json.dumps({"event": event})
    except ValueError as e:
        return _json_error(str(e))
    except Exception as e:
        logger.exception("tool handler failed")
        return _json_error(str(e))


def update_event(args: dict, **kwargs) -> str:
    """
    Update an existing event.

    Args:
        args (dict): A dictionary of arguments.
            * event_id (str): The ID of the event to update.
            * title (str, optional): The new title of the event.
            * description (str, optional): The new description of the event.
            * start_time (str, optional): The new start time of the event.
            * end_time (str, optional): The new end time of the event.
            * reminder_minutes_before (int, optional): The new reminder minutes before the event.
            * completed_at (null, optional): Set to null to mark the event as active again.
        kwargs: Additional keyword arguments.

    Returns:
        str: JSON string indicating success or error.
    """
    event_id = args.get("event_id", "").strip()
    if not event_id:
        return _json_error("event_id is required")

    fields = {}
    for key in ("title", "description", "start_time", "end_time", "reminder_minutes_before", "completed_at"):
        if key in args:
            fields[key] = args[key]

    if not fields:
        return _json_error("at least one field to update is required")

    try:
        event = store.modify_event(event_id, **fields)
        if event is None:
            return _json_error(f"Event '{event_id}' not found")
        return json.dumps({"success": True, "event": event})
    except ValueError as e:
        return _json_error(str(e))
    except Exception as e:
        logger.exception("tool handler failed")
        return _json_error(str(e))


def delete_event(args: dict, **kwargs) -> str:
    """
    Delete an event by its ID.

    Args:
        args (dict): A dictionary of arguments.
            * event_id (str): The ID of the event to delete.
        kwargs: Additional keyword arguments.

    Returns:
        str: JSON string indicating success or error.
    """
    event_id = args.get("event_id", "").strip()
    if not event_id:
        return _json_error("event_id is required")

    try:
        deleted = store.remove_event(event_id)
        if not deleted:
            return _json_error(f"Event '{event_id}' not found")
        return json.dumps({"success": True, "deleted": True})
    except ValueError as e:
        return _json_error(str(e))
    except Exception as e:
        logger.exception("tool handler failed")
        return _json_error(str(e))


def mark_event_complete(args: dict, **kwargs) -> str:
    """
    Mark an event as complete. Completed events are excluded from the agent's
    context injection and (when show_completed=true) appear in a separate
    'completed' section in list_events. Idempotent: marking an already-completed
    event is a no-op.

    Args:
        args (dict): A dictionary of arguments.
            * event_id (str): The ID of the event to mark complete.
        kwargs: Additional keyword arguments.

    Returns:
        str: JSON string indicating success or error.
    """
    event_id = args.get("event_id", "").strip()
    if not event_id:
        return _json_error("event_id is required")

    try:
        event = store.mark_event_complete(event_id)
        if event is None:
            return _json_error(f"Event '{event_id}' not found")
        return json.dumps({"success": True, "event": event})
    except ValueError as e:
        return _json_error(str(e))
    except Exception as e:
        logger.exception("tool handler failed")
        return _json_error(str(e))
