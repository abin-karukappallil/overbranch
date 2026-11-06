"""
`python -m tex_runner` — serve the compile sandbox on 0.0.0.0:${TEX_RUNNER_PORT:-8001}.

Run from `backend/` (the package is standalone: FastAPI + uvicorn + TeX, nothing else).
"""

import os

import uvicorn

from .server import create_app


def main() -> None:
    port = int(os.getenv("TEX_RUNNER_PORT") or 8001)
    host = os.getenv("TEX_RUNNER_HOST") or "0.0.0.0"
    uvicorn.run(create_app(), host=host, port=port, workers=1, proxy_headers=False,
                server_header=False, log_level=os.getenv("TEX_RUNNER_LOG_LEVEL") or "info")


if __name__ == "__main__":
    main()
