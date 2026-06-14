from __future__ import annotations

import logging

from . import plugin, schemas, store, tools

logger = logging.getLogger(__name__)


_TOOLS = (
    ("add_event", schemas.ADD_EVENT, "Create a scheduled event or reminder."),
    ("add_events", schemas.ADD_EVENTS, "Create multiple scheduled events at once."),
    ("list_events", schemas.LIST_EVENTS, "List scheduled events."),
    ("get_event", schemas.GET_EVENT, "Get details of a scheduled event."),
    ("update_event", schemas.UPDATE_EVENT, "Update a scheduled event."),
    ("delete_event", schemas.DELETE_EVENT, "Delete a scheduled event."),
    ("mark_event_complete", schemas.MARK_EVENT_COMPLETE,
     "Mark a scheduled event as complete."),
)


def register(ctx) -> None:
    logger.info("registering plugin")
    store.init_store()
    ctx.register_hook("pre_llm_call", plugin._inject_context)
    ctx.register_hook("on_session_start", plugin._inject_context)
    for name, schema, description in _TOOLS:
        ctx.register_tool(
            name=name,
            toolset="scheduler",
            schema=schema,
            handler=getattr(tools, name),
            description=description,
        )
