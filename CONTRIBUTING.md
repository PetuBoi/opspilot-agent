# Contributing

Install Python 3.13 and uv, then run `uv sync --locked`. Use feature branches.
Before submitting changes run `uv run ruff check .`, `uv run ruff format --check .`,
`uv run pytest -q`, and the offline CLI pipeline in README.md.
Add behavioral tests for state transitions, evidence validity or data leakage when changing them.
Do not commit downloaded datasets, model binaries, runtime databases or credentials.
Keep benchmark provenance and synthetic/real labels intact. Explain methodology changes.

Public contributions use MIT for original code. Third-party datasets retain their own licenses.
