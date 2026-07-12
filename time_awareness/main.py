import json

from time_awareness import plugin

if __name__ == "__main__":
    print(json.dumps(plugin.inject_context(), indent=4))
