# Logging Convention

This is the logging convention for the `gis_utils_public` package.

## Passive Logging

The package uses passive logging. Each module calls `logging.getLogger(__name__)` and never forces its own logging configuration. This means:

- The package does not overwrite the logging setup of the application that imports it.
- Log messages from `gis_utils_public` automatically flow into whatever handlers the calling application has configured.
- The caller (script, pipeline, or notebook) is always the logging owner.

## Why Passive Logging Matters for Packages

A package is imported by many different callers — scripts, pipelines, notebooks, and tests. Each caller owns its own logging configuration. If a package called `logging.basicConfig(...)` on import, it would silently overwrite whatever the caller already set up, causing missing output, wrong formats, or duplicate log lines. Passive logging avoids this by leaving all configuration to the application that imports the package.

## What This Means for Package Code

Do:

- Use `logging.getLogger(__name__)` at module level.
- Call `logger.info(...)`, `logger.warning(...)`, `logger.error(...)` as needed.

Do not:

- Call `logging.basicConfig(...)` anywhere in package code.
- Call `logging.root.setLevel(...)` or add handlers to the root logger.
- Use `print(...)` for operational messages.

## Example

```python
import logging

logger = logging.getLogger(__name__)

def resolve_sde_path(config: dict) -> str:
    """Resolve SDE connection path from config."""
    logger.info("Resolving SDE path for database: %s", config.get("database"))
    # ...
```

The calling application (for example `dp-gis`) controls where these messages go.
