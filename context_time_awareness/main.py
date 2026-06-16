from __future__ import annotations

import json
import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from context_time_awareness import plugin, store, tools
else:
    from . import plugin, store, tools


def main() -> None:
    store.init_store()
    result = plugin._inject_context(session_id="test-session")
    print(json.dumps(result, indent=4))

    # Create a sample event
    result = tools.add_event({"title": "Sample Event", "start_time": "2025-01-01T10:00:00", "end_time": "2025-01-01T11:00:00"})
    print(json.dumps(result, indent=4))



if __name__ == "__main__":
    main()
