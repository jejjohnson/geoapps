"""``geoapps-worker`` command line.

geoapps-worker run                          # poll the job queue forever
geoapps-worker sync                         # mirror registered steps into core.etl
geoapps-worker submit seed_demo '{"n": 20}' # queue a job
geoapps-worker once                         # run one queued job, if any
geoapps-worker list                         # show registered steps
"""

import argparse
import json
import logging

from geoapps_db import repo, session_scope
from geoapps_workers import runner  # registers every step
from geoapps_workers.registry import REGISTRY, sync_registry


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="geoapps-worker")
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--poll", type=float, default=2.0)
    sub.add_parser("sync")
    sub.add_parser("once")
    sub.add_parser("list")
    s = sub.add_parser("submit")
    s.add_argument("step")
    s.add_argument("params", nargs="?", default="{}")
    args = parser.parse_args(argv)

    if args.cmd == "run":
        runner.run_forever(args.poll)
    elif args.cmd == "sync":
        with session_scope() as session:
            print(f"registered {sync_registry(session)} steps")
    elif args.cmd == "once":
        print(runner.run_once())
    elif args.cmd == "list":
        for step in REGISTRY.values():
            print(
                f"{step.name:20} {step.version:8} writes {', '.join(step.writes) or '-'}  {step.description}"
            )
    elif args.cmd == "submit":
        if args.step not in REGISTRY:
            raise SystemExit(f"unknown step {args.step!r}; known: {', '.join(sorted(REGISTRY))}")
        params = REGISTRY[args.step].params.model_validate(json.loads(args.params)).model_dump()
        with session_scope() as session:
            sync_registry(session)
            job = repo.enqueue_job(session, etl=args.step, params=params, submitted_by="cli")
            print(job.id)


if __name__ == "__main__":
    main()
