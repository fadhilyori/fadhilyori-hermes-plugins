# time_awareness

Injects the current local time into the LLM context on every turn so the agent understands the present time and day.

**Hook used:** `pre_llm_call`

## Behavior

On every `pre_llm_call`, the plugin resolves the host's local timezone and injects a single context line:

```text
Current local time: 2024-06-15 14:30 WIB (Saturday, Asia/Jakarta)
```

### Fallback

If the local timezone cannot be determined (e.g. `tzlocal` or `ZoneInfo` fails), the plugin falls back to **UTC** rather than blocking the LLM call. This guarantees the hook never disrupts the agent runtime.

## Dependencies

- `tzlocal` — resolves the host's local timezone name.

## Tests

```bash
make test PLUGIN=time_awareness
```
