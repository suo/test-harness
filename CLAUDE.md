When you make a change, if the change is user-visible or architecturally
significant, update the README.md file to reflect your change.

## Running tests

```
uv run pytest tests/ -v
```

To update snapshots:

```
uv run pytest tests/ -v --snapshot-update
```
