#!/usr/bin/env python3
"""Lightweight HTTP server that serves bcm-process-metrics.sh output for Prometheus scraping."""
import http.server, subprocess, sys, os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9256
SCRIPT = "/cm/local/apps/cmd/scripts/monitoring/bcm-process-metrics.sh"
if not os.path.exists(SCRIPT):
    SCRIPT = "/tmp/bcm-process-metrics.sh"

class MetricsHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            r = subprocess.run(["bash", SCRIPT], capture_output=True, text=True, timeout=30)
            body = r.stdout.encode()
        except Exception as e:
            body = f"# error: {e}\n".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a):
        pass

if __name__ == "__main__":
    print(f"Serving metrics on :{PORT}", flush=True)
    http.server.HTTPServer(("0.0.0.0", PORT), MetricsHandler).serve_forever()
