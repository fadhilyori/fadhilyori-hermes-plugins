"""Tool schemas in OpenAI function-calling format."""

_EVENT_PROPS = {
    "title": {"type": "string", "description": "Event title."},
    "start_time": {
        "type": "string",
        "description": (
            "ISO 8601 start time, e.g. '2024-01-15T14:30:00' "
            "or '2024-01-15T14:30:00+07:00'."
        ),
    },
    "end_time": {"type": "string", "description": "Optional ISO 8601 end time."},
    "description": {"type": "string", "description": "Optional event details."},
    "reminder_minutes_before": {
        "type": "integer",
        "description": (
            "Minutes before the event to inject it into the agent's context. "
            "Default is 5."
        ),
    },
}

ADD_EVENT = {
    "name": "add_event",
    "description": (
        "Create a new scheduled event or reminder. "
        "Times without a timezone are interpreted as local time."
    ),
    "parameters": {
        "type": "object",
        "properties": _EVENT_PROPS,
        "required": ["title", "start_time"],
    },
}

ADD_EVENTS = {
    "name": "add_events",
    "description": (
        "Create multiple scheduled events at once. "
        "Useful when the user lists several items in one message."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "events": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": _EVENT_PROPS,
                    "required": ["title", "start_time"],
                },
                "description": "List of events to create.",
            },
        },
        "required": ["events"],
    },
}

LIST_EVENTS = {
    "name": "list_events",
    "description": "List scheduled events.",
    "parameters": {
        "type": "object",
        "properties": {
            "filter": {
                "type": "string",
                "enum": ["upcoming", "past", "today"],
                "description": (
                    "upcoming = next 2 weeks, "
                    "past = already started, "
                    "today = today's events in local time."
                ),
                "default": "upcoming",
            },
            "start_date": {
                "type": "string",
                "description": (
                    "Inclusive start of a date range in local time, "
                    "format 'YYYY-MM-DD'. When set, overrides 'filter'."
                ),
            },
            "end_date": {
                "type": "string",
                "description": (
                    "Inclusive end of a date range in local time, "
                    "format 'YYYY-MM-DD'. Requires start_date. "
                    "When set, overrides 'filter'."
                ),
            },
            "limit": {
                "type": "integer",
                "description": (
                    "Maximum number of events to return. Default is 10. "
                    "Capped at 100."
                ),
                "default": 10,
            },
            "show_completed": {
                "type": "boolean",
                "description": (
                    "Controls the response shape. When false, the response "
                    "is a single 'events' list. When true, the response is "
                    "split into two sections: 'active' (events that have not "
                    "been completed) and 'completed' (events that have been "
                    "marked complete). The 'filter' or date range applies to "
                    "both the active and completed sections."
                ),
                "default": False,
            },
        },
    },
}

GET_EVENT = {
    "name": "get_event",
    "description": "Get details of a single scheduled event.",
    "parameters": {
        "type": "object",
        "properties": {
            "event_id": {"type": "string", "description": "Event ID."},
        },
        "required": ["event_id"],
    },
}

UPDATE_EVENT = {
    "name": "update_event",
    "description": (
        "Update an existing event. Only provided fields are changed. "
        "Set end_time to null to remove it. Set completed_at to null "
        "to unmark a completed event; to mark complete, use mark_event_complete."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "event_id": {"type": "string", "description": "Event ID."},
            "title": {"type": "string", "description": "New title."},
            "start_time": {"type": "string", "description": "ISO 8601 start time."},
            "end_time": {
                "type": ["string", "null"],
                "description": "ISO 8601 end time, or null to remove it.",
            },
            "description": {"type": "string", "description": "New description."},
            "reminder_minutes_before": {
                "type": "integer",
                "description": "Minutes before the event to inject into context.",
            },
            "completed_at": {
                "type": "null",
                "description": (
                    "Must be null. Use mark_event_complete to mark an event complete."
                ),
            },
        },
        "required": ["event_id"],
    },
}

DELETE_EVENT = {
    "name": "delete_event",
    "description": "Delete a scheduled event.",
    "parameters": {
        "type": "object",
        "properties": {
            "event_id": {"type": "string", "description": "Event ID."},
        },
        "required": ["event_id"],
    },
}

MARK_EVENT_COMPLETE = {
    "name": "mark_event_complete",
    "description": (
        "Mark a scheduled event as complete. "
        "Completed events are excluded from context injection and "
        "appear in list_events only when show_completed=true. "
        "Idempotent: marking an already-complete event is a no-op."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "event_id": {"type": "string", "description": "Event ID."},
        },
        "required": ["event_id"],
    },
}
