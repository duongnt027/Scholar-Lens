"""python -m scholarlens.app [--host 0.0.0.0] [--port 7860]"""
import argparse

import uvicorn


def main():
    ap = argparse.ArgumentParser(prog="scholarlens.app")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7860)
    a = ap.parse_args()
    uvicorn.run("scholarlens.app.server:app", host=a.host, port=a.port, log_level="info")


if __name__ == "__main__":
    main()
