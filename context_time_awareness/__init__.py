from __future__ import annotations

import logging

from . import plugin, schemas, store, tools

logger = logging.getLogger(__name__)


def register(ctx) -> None:
    logger.info("registering plugin")
    store.init_store()
    ctx.register_hook("pre_llm_call", plugin._inject_context)
    ctx.register_hook("on_session_start", plugin._inject_context)

    ctx.register_tool(
        name="add_event",
        toolset="scheduler",
        schema=schemas.ADD_EVENT,
        handler=tools.add_event,
        description="Create a scheduled event or reminder.",
    )
    ctx.register_tool(
        name="add_events",
        toolset="scheduler",
        schema=schemas.ADD_EVENTS,
        handler=tools.add_events,
        description="Create multiple scheduled events at once.",
    )
    ctx.register_tool(
        name="list_events",
        toolset="scheduler",
        schema=schemas.LIST_EVENTS,
        handler=tools.list_events,
        description="List scheduled events.",
    )
    ctx.register_tool(
        name="get_event",
        toolset="scheduler",
        schema=schemas.GET_EVENT,
        handler=tools.get_event,
        description="Get details of a scheduled event.",
    )
    ctx.register_tool(
        name="update_event",
        toolset="scheduler",
        schema=schemas.UPDATE_EVENT,
        handler=tools.update_event,
        description="Update a scheduled event.",
    )
    ctx.register_tool(
        name="delete_event",
        toolset="scheduler",
        schema=schemas.DELETE_EVENT,
        handler=tools.delete_event,
        description="Delete a scheduled event.",
    )
    ctx.register_tool(
        name="mark_event_complete",
        toolset="scheduler",
        schema=schemas.MARK_EVENT_COMPLETE,
        handler=tools.mark_event_complete,
        description="Mark a scheduled event as complete.",
    )
