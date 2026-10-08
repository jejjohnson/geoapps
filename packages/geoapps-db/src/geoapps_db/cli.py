"""``geoapps-db`` command line: migrations without an alembic.ini on disk.

geoapps-db upgrade              # migrate to head (run by the API container on start)
geoapps-db downgrade base       # gate A1: round trip on an empty database
geoapps-db revision -m "..."    # autogenerate a new migration (developers)
"""

import argparse
from importlib.resources import files

from alembic import command
from alembic.config import Config

from geoapps_db.session import database_url


def alembic_config(url: str | None = None) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(files("geoapps_db") / "migrations"))
    cfg.set_main_option("sqlalchemy.url", (url or database_url()).replace("%", "%%"))
    return cfg


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="geoapps-db")
    sub = parser.add_subparsers(dest="cmd", required=True)
    up = sub.add_parser("upgrade")
    up.add_argument("target", nargs="?", default="head")
    down = sub.add_parser("downgrade")
    down.add_argument("target", nargs="?", default="-1")
    rev = sub.add_parser("revision")
    rev.add_argument("-m", "--message", required=True)
    sub.add_parser("current")
    args = parser.parse_args(argv)

    cfg = alembic_config()
    if args.cmd == "upgrade":
        command.upgrade(cfg, args.target)
    elif args.cmd == "downgrade":
        command.downgrade(cfg, args.target)
    elif args.cmd == "revision":
        command.revision(cfg, message=args.message, autogenerate=True)
    elif args.cmd == "current":
        command.current(cfg, verbose=True)


if __name__ == "__main__":
    main()
