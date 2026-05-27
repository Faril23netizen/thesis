#!/bin/bash
echo "=== Aquaculture System Monitor ==="
echo ""
echo "Last 5 log entries:"
tail -5 results/hasil_real/fql.log
echo ""
echo "Current phase:"
grep -E "PHASE|DQN.*Real steps" results/hasil_real/fql.log | tail -3
echo ""
echo "Total steps:"
wc -l results/hasil_real/comparison.csv
echo ""
echo "File sizes:"
ls -lh results/hasil_real/*.{csv,json,log} 2>/dev/null
