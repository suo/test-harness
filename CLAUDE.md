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

## Releasing

1. Update the version in `pyproject.toml` (e.g. `version = "0.2.0"`).
2. Run `uv lock` to sync the lock file.
3. Add an entry to `CHANGELOG.md` under a heading for the new version.
4. Commit these changes (e.g. `git commit -m "Release 0.2.0"`).
5. Create a git tag matching the version: `git tag v0.2.0`
6. Push the commit and tag: `git push && git push --tags`

Pushing the tag triggers the GitHub Actions `publish.yml` workflow, which
builds the package and publishes it to PyPI.
