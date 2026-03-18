#!/bin/bash
# Start metrics HTTP server on port 9256 for Prometheus scraping
pkill -f metrics-server.py 2>/dev/null
sleep 1
nohup python3 /tmp/metrics-server.py 9256 > /var/log/ms.log 2>&1 &
sleep 3
echo "PID=$(pgrep -f metrics-server.py)"
echo "LOG:"
cat /var/log/ms.log
echo "TEST:"
curl -s --max-time 5 http://localhost:9256 2>&1 | head -3
