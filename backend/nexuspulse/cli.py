"""Command-line entry point: python -m nexuspulse <command>."""

from __future__ import annotations

import argparse
import json
import logging

from .db import SessionLocal, init_db


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="nexuspulse")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("seed-synthetic", help="generate synthetic Riot-format matches")
    p.add_argument("--n", type=int, default=400)
    p.add_argument("--seed", type=int, default=42)

    p = sub.add_parser("collect-match", help="fetch one match + timeline from the Riot API")
    p.add_argument("match_id")

    p = sub.add_parser("collect-player", help="fetch recent ranked matches for a Riot ID (Name#TAG)")
    p.add_argument("riot_id")
    p.add_argument("--count", type=int, default=20)

    p = sub.add_parser("crawl", help="snowball-crawl high-tier ranked matches for training")
    p.add_argument("--max-matches", type=int, default=500)
    p.add_argument("--tier", default="challenger", choices=["challenger", "grandmaster", "master"])

    p = sub.add_parser("train", help="train all models on the local cache")
    p.add_argument("--source", choices=["riot", "synthetic"], default=None)

    p = sub.add_parser("serve", help="run the API server")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    init_db()

    if args.cmd == "serve":
        import uvicorn

        uvicorn.run("nexuspulse.api:app", host=args.host, port=args.port)
        return

    with SessionLocal() as session:
        if args.cmd == "seed-synthetic":
            from .ingest import seed_synthetic

            print(f"seeded {seed_synthetic(session, args.n, args.seed)} synthetic matches")
        elif args.cmd in ("collect-match", "collect-player", "crawl"):
            from .ingest import collect_match, collect_player, crawl
            from .riot_client import RiotClient

            client = RiotClient()
            if not client.configured:
                raise SystemExit("RIOT_API_KEY is not set (env var or backend/.env)")
            if args.cmd == "collect-match":
                print(json.dumps(collect_match(session, client, args.match_id), indent=2))
            elif args.cmd == "collect-player":
                name, _, tag = args.riot_id.partition("#")
                if not tag:
                    raise SystemExit("Riot ID must look like Name#TAG")
                print(json.dumps(collect_player(session, client, name, tag, args.count), indent=2))
            else:
                print(f"crawled {crawl(session, client, args.max_matches, args.tier)} new matches")
        elif args.cmd == "train":
            from .models.registry import train_all

            bundle = train_all(session, args.source)
            print(json.dumps(bundle.manifest, indent=2))


if __name__ == "__main__":
    main()
