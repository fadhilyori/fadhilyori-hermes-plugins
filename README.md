# hermes-plugins

A collection of plugins for the Hermes agent runtime.

## Installation

### All plugins (git clone)

Install all plugins by cloning the repository into your Hermes plugins directory.

```bash
git clone https://github.com/fadhilyori/fadhilyori-hermes-plugins ~/.hermes/plugins/
```

Then check the list of available plugins with

```bash
hermes plugins list --user
```

To update the plugins, simply pull the latest changes from the repository:

```bash
cd ~/.hermes/plugins/fadhilyori-hermes-plugins
git pull
```

### Specific plugins

To install a specific plugin, use this command:

```bash
hermes plugins install fadhilyori/fadhilyori-hermes-plugins/time_awareness
```

To update a specific plugin, add `--force` to the install command:

```bash
hermes plugins install fadhilyori/fadhilyori-hermes-plugins/DIRECTORY_NAME --force
```

## Available Plugins

- [time_awareness](./time_awareness/README.md) - Injects the current local time into the LLM context on every turn so the agent understands the present time and day.

## Development

Targets are defined in the `Makefile`:

- `make list` - List available plugins.
- `make test PLUGIN=<name>` - Run tests for a single plugin.
- `make test-all` - Run tests for all plugins.
- `make clean` - Remove test artifacts (`__pycache__/`, `*.db`).
- `make help` - Show the available targets.
