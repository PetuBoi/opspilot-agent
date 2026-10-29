"""Command line entry point."""

from pathlib import Path

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
    from opspilot.classifier import train_classifier

    typer.echo(train_classifier("demo", Path("artifacts/demo"), Path("reports/synthetic")))


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


@app.command("train-classifier")
def train(dataset: str = "it-support") -> None:
    """Select TF-IDF baselines on grouped training validation, then evaluate held-out test."""
    from opspilot.classifier import train_classifier

    kind = "real" if dataset == "it-support" else "synthetic"
    try:
        typer.echo(train_classifier(dataset, Path("artifacts") / dataset, Path("reports") / kind))
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


@app.command("evaluate")
def evaluate(dataset: str = "demo") -> None:
    """Measure synthetic agent/retrieval or reproduce authentic classifier evaluation."""
    from opspilot.config import Settings
    from opspilot.evaluation import evaluate_agent

    if dataset == "demo":
        typer.echo(evaluate_agent(Settings(), Path("artifacts"), Path("reports/synthetic")))
    elif dataset == "it-support":
        train(dataset)
    else:
        raise typer.BadParameter("Supported datasets: demo, it-support")


@app.command("report")
def report(dataset: str = "demo") -> None:
    """Print computed report locations and results; never invent missing metrics."""
    import json

    if dataset not in {"demo", "it-support"}:
        raise typer.BadParameter("Supported datasets: demo, it-support")
    directory = Path("reports") / ("synthetic" if dataset == "demo" else "real")
    for path in sorted(directory.glob("*summary.json")):
        typer.echo(f"{path}: {json.loads(path.read_text('utf-8'))}")
