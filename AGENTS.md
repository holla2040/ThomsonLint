# ThomsonLint Agent Instructions

## Python environment

This repository uses Python scripts and pytest-based tests.

Before running tests, create or update a local virtual environment:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

Use the venv Python for validation:

```bash
python -m py_compile scripts/<script>.py tests/<test_file>.py
python -m pytest tests/<test_file>.py -v
```

Do not claim pytest passed unless pytest actually ran.

If the environment has python3 but not python, activate .venv first. After activation, python should resolve to .venv/bin/python.

## Project constraints

Do not run the full ThomsonLint workflow unless explicitly requested.

For staged PR work, run only the focused tests for the changed script.

Do not delete user project files, exports, inputs, datasheets, or local artifacts.
