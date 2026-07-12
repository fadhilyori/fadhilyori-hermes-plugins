from __future__ import annotations

import logging

from . import plugin

logger = logging.getLogger(__name__)

def register(ctx) -> None:
    logger.info("registering plugin")

    # Register hooks
    ctx.register_hook("pre_llm_call", plugin.inject_context)
