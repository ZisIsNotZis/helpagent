# helpagent

A small-model coding harness built around typed kernel envelopes, task trees, and a fake-model layer. The repository includes Python harness components, schemas, tests, and design documentation.

## Requirements

Python 3.12 or newer. Install dependencies in an isolated environment using your preferred Python package manager; the project metadata is in [`pyproject.toml`](pyproject.toml).

## Development

```sh
pytest
```

The canonical fast unit and contract test paths are configured in `pyproject.toml`. Broader integration tests may require a local model server; see [`docs/TEST_PLAN.md`](docs/TEST_PLAN.md) before running them. Architecture and interfaces are documented under [`docs/`](docs/).
