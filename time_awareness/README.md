# time_awareness

Injects the current local time into the LLM context on every turn so the agent understands the present time and day.

**Hook used:** `pre_llm_call`

## Behavior

On every `pre_llm_call`, the plugin reads the timezone configured for
Hermes Agent and injects a single context line with the current local time:

```text
2024-06-15T14:30+07:00 Sat Asia/Jakarta
```

### Resolution order

The timezone is read from Hermes Agent's configuration, in this order:

1. The `HERMES_TIMEZONE` environment variable (IANA name, e.g. `Asia/Jakarta`).
2. The `timezone` key in `~/.hermes/config.yaml`.
3. The server's local time (used when no explicit configuration is present).

### Fallback

If the configured timezone is invalid or unavailable, the plugin falls back
to the server's local time rather than blocking the LLM call. The hook
never disrupts the agent runtime.

### Relationship to Hermes Agent

Hermes Agent already injects a date line into the system prompt at session
start. This plugin complements that by adding minute precision and the
IANA zone name on every turn.

## Dependencies

None beyond `hermes-agent`, which the parent project already requires.

## Tests

```bash
make test PLUGIN=time_awareness
```
