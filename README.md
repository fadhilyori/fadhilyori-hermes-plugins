# hermes-plugins

A collection of plugins for the Hermes agent runtime.

## Plugins

- [time_awareness](./time_awareness/README.md) - Injects the current local time into the LLM context on every turn so the agent understands the present time and day.

## Development

Targets are defined in the `Makefile`:

- `make list` - List available plugins.
- `make test PLUGIN=<name>` - Run tests for a single plugin.
- `make test-all` - Run tests for all plugins.
- `make clean` - Remove test artifacts (`__pycache__/`, `*.db`).
- `make help` - Show the available targets.
