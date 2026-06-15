# hermes-plugins

A collection of plugins for the Hermes agent runtime.

## Plugins

- [context_time_awareness](./context_time_awareness/README.md) - Injects current local time into LLM context on every turn, plus elapsed time since the last user message, with lightweight event scheduling.

## Development

Targets are defined in the `Makefile`:

- `make list` - List available plugins.
- `make test PLUGIN=<name>` - Run tests for a single plugin.
- `make test-all` - Run tests for all plugins.
- `make clean` - Remove test artifacts (`__pycache__/`, `*.db`).
- `make help` - Show the available targets.
