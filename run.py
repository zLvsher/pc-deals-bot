"""Punto di ingresso: avvia il server FastAPI (bot + GUI) su http://127.0.0.1:8000

Uso:
    python run.py            # default, porta 8000
    python run.py --port 9000
"""
from __future__ import annotations

import argparse
import logging

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="PC Deals Bot")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    print(f"\n🖥️  PC Deals Bot → apri http://{args.host}:{args.port} nel browser\n")
    uvicorn.run("ui.server:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
