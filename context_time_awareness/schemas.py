"""Tool schemas in OpenAI function-calling format."""

_ADD_EVENT_ITEM = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "Event title",
        },
        "start_time": {
            "type": "string",
            "description": (
                "ISO 8601 start time, e.g. '2024-01-15T14:30:00' "
                "or '2024-01-15T14:30:00+07:00'"
            ),
        },
        "end_time": {
            "type": "string",
            "description": "Optional ISO 8601 end time",
        },
        "description": {
            "type": "string",
            "description": "Optional event details",
        },
        "reminder_minutes_before": {
            "type": "integer",
            "description": (
                "Minutes before the event to include it in the agent's context. "
                "Default is 5."
            ),
        },
    },
    "required": ["title", "start_time"],
}

ADD_EVENT = {
    "name": "add_event",
    "description": (
        "Create a new scheduled event or reminder for the user. "
        "Times without a timezone are interpreted as local time."
    ),
    "parameters": {
        "type": "object",
        "properties": _ADD_EVENT_ITEM["properties"],
        "required": ["title", "start_time"],
    },
}

ADD_EVENTS = {
    "name": "add_events",
    "description": (
        "Create multiple scheduled events at once. "
        "Useful when the user lists several schedule items in one message."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "events": {
                "type": "array",
                "items": _ADD_EVENT_ITEM,
                "description": "List of events to create",
            },
        },
        "required": ["events"],
    },
}

LIST_EVENTS = {
    "name": "list_events",
    "description": "List scheduled events for the user.",
    "parameters": {
        "type": "object",
        "properties": {
            "filter": {
                "type": "string",
                "enum": ["upcoming", "past", "today"],
                "description": (
                    "upcoming = next 2 weeks, "
                    "past = already started, "
                    "today = today's events in local time"
                ),
                "default": "upcoming"
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of events to return (default 10)",
                "default": 10
            },
            "show_completed": {
                "type": "boolean",
                "description": (
                    "When true, the response includes a separate 'completed' "
                    "section listing events that have been marked complete."
                ),
                "default": False
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
            "event_id": {
                "type": "string",
                "description": "Event ID",
            },
        },
        "required": ["event_id"],
    },
}

UPDATE_EVENT = {
    "name": "update_event",
    "description": (
        "Update an existing scheduled event. "
        "Only provided fields are changed."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "event_id": {
                "type": "string",
                "description": "Event ID",
            },
            "title": {"type": "string"},
            "start_time": {
                "type": "string",
                "description": "ISO 8601 start time",
            },
            "end_time": {
                "type": ["string", "null"],
                "description": "Optional ISO 8601 end time. Set to null to remove.",
            },
            "description": {"type": "string"},
            "reminder_minutes_before": {
                "type": "integer",
                "description": "Minutes before the event to include it in context",
            },
            "completed_at": {
                "type": "null",
                "description": (
                    "Set to null to mark the event as active again (unmark). "
                    "To mark an event complete, use mark_event_complete."
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
            "event_id": {
                "type": "string",
                "description": "Event ID",
            },
        },
        "required": ["event_id"],
    },
}

MARK_EVENT_COMPLETE = {
    "name": "mark_event_complete",
    "description": (
        "Mark a scheduled event as complete. "
        "Completed events no longer appear in the agent's context injection. "
        "When list_events is called with show_completed=true, they appear in "
        "a separate 'completed' section."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "event_id": {
                "type": "string",
                "description": "Event ID",
            },
        },
        "required": ["event_id"],
    },
}
