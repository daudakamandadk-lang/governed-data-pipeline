"""Neutral customers/orders exercise for snapshot extraction and trigger CDC."""
import argparse
from contextlib import closing
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3

from .database_pipeline import DatabaseJobConfig, SqliteDatabasePipeline
from .sqlite_cdc import SqliteChangeCapture


def demo_config(workspace=None):
    root = Path(workspace or Path.cwd()).resolve() / "data/local/database_demo"
    schemas = {
        "customers": {"primary_key": "customer_id", "columns": {
            "customer_id": {"dtype": "string", "required": True, "unique": True},
            "region": {"dtype": "category", "required": True, "allowed": ["North", "South"]},
            "active": {"dtype": "boolean", "required": True}}},
        "orders": {"primary_key": "order_id", "columns": {
            "order_id": {"dtype": "string", "required": True, "unique": True},
            "customer_id": {"dtype": "string", "required": True, "foreign_key": "customers.customer_id"},
            "order_date": {"dtype": "date", "required": True},
            "quantity": {"dtype": "integer", "required": True, "min": 1},
            "total": {"dtype": "float", "required": True, "min": 0}}},
    }
    return DatabaseJobConfig(root / "source.sqlite", root / "target.sqlite", schemas,
                             date_formats={"orders": {"order_date": "%Y-%m-%d"}}, job_name="customers_orders")


def initialize_demo(config):
    """Initialize only an absent synthetic source; never overwrite a database."""
    source = Path(config.source_path)
    if source.exists():
        return False
    source.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source)) as connection:
        with connection:
            connection.execute("CREATE TABLE customers(customer_id TEXT PRIMARY KEY NOT NULL,region TEXT,active INTEGER)")
            connection.execute("CREATE TABLE orders(order_id TEXT PRIMARY KEY NOT NULL,customer_id TEXT,"
                               "order_date TEXT,quantity INTEGER,total REAL)")
            connection.executemany("INSERT INTO customers VALUES(?,?,?)", [("C001", "North", 1), ("C002", "South", 0)])
            connection.executemany("INSERT INTO orders VALUES(?,?,?,?,?)", [
                ("O001", "C001", "2026-10-05", 1, 10.0), ("O002", "C002", "2026-10-05", 1, 20.0)])
    return True


def mutate_demo(config):
    """Apply five known fixture changes in one source transaction; repeat is safe."""
    with closing(sqlite3.connect(config.source_path)) as connection:
        with connection:
            exists = connection.execute("SELECT 1 FROM orders WHERE order_id='O003'").fetchone()
            if exists:
                return False
            if connection.execute("SELECT COUNT(*) FROM orders WHERE order_id IN ('O001','O002')").fetchone()[0] != 2:
                raise ValueError("Mutation exercise requires the original two-order demo")
            connection.execute("UPDATE orders SET quantity=2,total=25 WHERE order_id='O001'")
            connection.execute("INSERT INTO customers VALUES('C003','North',1)")
            connection.execute("INSERT INTO orders VALUES('O003','C003','2026-10-05',1,30)")
            connection.execute("DELETE FROM orders WHERE order_id='O002'")
            connection.execute("DELETE FROM customers WHERE customer_id='C002'")
    return True


def config_from_json(path):
    settings = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in ("source_path", "database_path"):
        settings[key] = Path(settings[key]).resolve()
    return DatabaseJobConfig(**settings)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", choices=("bootstrap", "changes", "mutate"), default="bootstrap")
    parser.add_argument("--config", type=Path, help="Existing source and declared contracts; creates no sample")
    parser.add_argument("--install-capture", action="store_true", help="Explicitly install reviewed triggers on the selected source")
    arguments = parser.parse_args(argv)
    config = config_from_json(arguments.config) if arguments.config else demo_config()
    if arguments.config and arguments.action == "mutate":
        parser.error("mutate is available only for the synthetic demo")
    if not arguments.config:
        initialize_demo(config)
        SqliteChangeCapture(config.source_path, config.schemas).install()
    elif arguments.install_capture:
        SqliteChangeCapture(config.source_path, config.schemas).install()
    if arguments.action == "mutate":
        result = {"status": "source_changed" if mutate_demo(config) else "already_changed", "source": str(config.source_path)}
    else:
        pipeline = SqliteDatabasePipeline(config)
        result = asdict(pipeline.bootstrap() if arguments.action == "bootstrap" else pipeline.run_changes())
        result["committed_checkpoint"] = pipeline.checkpoint()
    print(json.dumps(result, indent=2, default=str))
    return result


def cli():
    main()


if __name__ == "__main__":
    cli()
