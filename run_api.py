"""Start the Earnings Engine API server."""

import uvicorn
from earnings_engine.port_utils import ensure_port_available

if __name__ == "__main__":
    port = 8000
    host = "0.0.0.0"
    killed = ensure_port_available(port=port, host="127.0.0.1")
    if killed:
        print(f"⚠️ Port {port} was occupied by PID(s) {killed}. Terminated conflicting process(es).")

    uvicorn.run(
        "earnings_engine.api.server:app",
        host=host,
        port=port,
        reload=True,
        log_level="info",
    )