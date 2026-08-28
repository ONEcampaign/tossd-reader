# tossd-reader

Python package to access TOSSD activity-level data

## Installation

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
# Install dependencies
uv sync
```


## Development

### Running Tests

```bash
uv run pytest
```

### Code Quality

```bash
# Run linter
uv run ruff check .

# Run formatter
uv run ruff format .

# Run type checker
uv run ty check src/tossd_reader
```

### Building

```bash
uv build
```



## Pre-commit Hooks

Pre-commit hooks are configured to run automatically. To manually run:

```bash
pre-commit run --all-files
```


## License

This project is licensed under the mit License - see the LICENSE file for details.

