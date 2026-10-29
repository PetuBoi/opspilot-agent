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


@app.command("index")
def index_knowledge() -> None:
    """Atomically replace the lexical index from local Markdown/plain text."""
    from opspilot.config import Settings
    from opspilot.retrieval import KnowledgeBase
    from opspilot.store import Store

    settings = Settings()
    typer.echo(
        KnowledgeBase(Store(settings.db_path)).index(settings.data_dir / "kb", settings.chunk_size)
    )


@app.command("download-dataset")
def download_dataset(source: str = "it-support") -> None:
    """Download pinned authentic classification data and generate EDA."""
    from pathlib import Path

    from opspilot.datasets import download, eda

    if source != "it-support":
        raise typer.BadParameter("Supported source: it-support")
    try:
        root = Path("data/external/it-support")
        typer.echo(download(root))
        typer.echo(eda(root, Path("reports/real")))
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
