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
