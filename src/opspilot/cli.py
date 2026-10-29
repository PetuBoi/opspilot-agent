"""Command line entry point."""

import typer

from opspilot import __version__

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    """Investigate fictional incidents with auditable human approval."""


@app.command()
def version() -> None:
    """Print the installed application version."""
    typer.echo(__version__)


@app.command("seed-demo")
def seed_demo() -> None:
    """Regenerate the original fictional environment; safe to repeat."""
    from opspilot.config import Settings
    from opspilot.demo import seed
    from opspilot.store import Store

    settings = Settings()
    typer.echo(seed(Store(settings.db_path), settings.data_dir / "kb"))
