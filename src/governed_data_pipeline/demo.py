"""A connected, synthetic-only classroom example; initializes samples if absent."""

import argparse
from dataclasses import asdict, replace
import json
import logging
from pathlib import Path

import pandas as pd

from .pipeline import GovernedPipeline, PipelineConfig
from .record_gates import GateThresholds


def sample_transactions(dirty=False):
    data = pd.DataFrame({
        "transaction_id": [1, 2, 3, 4, 5, 6],
        "customer_id": [" A001 ", "A002", "A003", "A004", "A005 ", "A006"],
        "amount": ["100", "200", "150", "300", "350", "450"],
        "active": ["true", "false", "true", "true", "false", "true"],
        "order_date": ["2026-10-01"] * 6,
        "snapshot_date": ["2026-10-05"] * 6,
    })
    if dirty:
        data.loc[2, "amount"] = "unknown"
        data.loc[3, "amount"] = "-5"
        data.loc[4, "order_date"] = "2026-10-07"
    return data


def example_config(scenario="clean", allow_quarantine=False, workspace=None):
    config = PipelineConfig.from_json(Path(__file__).with_name("demo_config.json"), workspace)
    # Different examples own distinct files and progress; existing data survives.
    folder = config.source.parent / scenario
    config = replace(config, job_name=f"{config.job_name}_{scenario}",
                     source=folder / "transactions.csv", database_path=folder / "target.db",
                     watermark_path=folder / "progress.json")
    if allow_quarantine:
        config.gate = GateThresholds(max_quarantine_rate=0.6, warn_quarantine_rate=0.0)
    return config


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=("clean", "dirty"), default="clean")
    parser.add_argument("--allow-quarantine", action="store_true",
                        help="Permit accepted rows after durable quarantine; maximum bad rate 60%%")
    parser.add_argument("--config", type=Path, help="Explicit JSON job configuration; does not generate a sample")
    arguments = parser.parse_args(argv)
    config = PipelineConfig.from_json(arguments.config) if arguments.config else example_config(
        arguments.scenario, arguments.allow_quarantine
    )
    if not arguments.config and not config.source.exists():
        config.source.parent.mkdir(parents=True, exist_ok=True)
        sample_transactions(arguments.scenario == "dirty").to_csv(config.source, index=False)
    result = GovernedPipeline(config).run()
    print(json.dumps(asdict(result), indent=2, default=str))
    print("Audit and target database:", config.database_path)
    return result


def cli():
    """Console entry point; main returns a result for Python callers."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()


if __name__ == "__main__":
    cli()
