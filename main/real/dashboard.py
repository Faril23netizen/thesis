#!/usr/bin/env python3
"""
dashboard.py - Real-time Dashboard for run_real.py
===================================================
Flask dashboard yang membaca state.json dari run_real.py

Usage:
  # Terminal 1: Jalankan sistem
  python3 main/real/run_real.py
  
  # Terminal 2: Jalankan dashboard
  python3 main/real/dashboard.py
  
  # Akses: http://<IP_RPi5>:5000
"""

import os
import sys
import json
import time
import socket
from flask import Flask, jsonify, render_template_string

# Path configuration
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESULTS_DIR = os.path.join(BASE_DIR, "results", "hasil_real")
STATE_JSON = os.path.join(RESULTS_DIR, "state.json")
COMPARISON_CSV = os.path.join(RESULTS_DIR, "comparison.csv")

app = Flask(__name__)

# HTML Template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Aquaculture Real Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #fff;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 {
            text-align: center;
            margin-bottom: 30px;
            font-size: 2.5em;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        .status-bar {
            background: rgba(255,255,255,0.1);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            text-align: center;
        }
        .status-connected {
            display: inline-block;
            padding: 10px 20px;
            border-radius: 25px;
            font-weight: bold;
            font-size: 1.2em;
        }
        .connected { background: #10b981; }
        .disconnected { background: #ef4444; }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        .card {
            background: rgba(255,255,255,0.1);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }
        .card h2 {
            font-size: 1.2em;
            margin-bottom: 15px;
            color: #fbbf24;
        }
        .metric {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin: 10px 0;
            padding: 10px;
            background: rgba(255,255,255,0.05);
            border-radius: 8px;
        }
        .metric-label {
            font-size: 0.9em;
            opacity: 0.8;
        }
        .metric-value {
            font-size: 1.5em;
            font-weight: bold;
        }
        .phase-badge {
            display: inline-block;
            padding: 5px 15px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 0.9em;
        }
        .phase-rb { background: #ef4444; }
        .phase-fql { background: #10b981; }
        .phase-dqn { background: #f59e0b; }
        .action-badge {
            display: inline-block;
            padding: 5px 15px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 0.9em;
            background: #3b82f6;
        }
        .footer {
            text-align: center;
            margin-top: 30px;
            opacity: 0.7;
            font-size: 0.9em;
        }
        .error {
            background: rgba(239, 68, 68, 0.2);
            border: 2px solid #ef4444;
            border-radius: 10px;
            padding: 20px;
            text-align: center;
            margin: 20px 0;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .pulse { animation: pulse 2s infinite; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🐟 Aquaculture Real-Time Dashboard</h1>
        
        <div class="status-bar">
            <div id="status" class="status-connected disconnected pulse">
                Connecting to system...
            </div>
        </div>

        <div id="error-msg" class="error" style="display: none;">
            <h3>⚠️ System Not Running</h3>
            <p>Please start the system first:</p>
            <code>python3 main/real/run_real.py</code>
        </div>

        <div id="content" style="display: none;">
            <div class="grid">
                <div class="card">
                    <h2>💧 Water Quality</h2>
                    <div class="metric">
                        <span class="metric-label">pH Level</span>
                        <span class="metric-value" id="pH">--</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Temperature</span>
                        <span class="metric-value" id="temp">--°C</span>
                    </div>
                </div>

                <div class="card">
                    <h2>🤖 AI Control</h2>
                    <div class="metric">
                        <span class="metric-label">Phase</span>
                        <span class="metric-value" id="phase">--</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Action</span>
                        <span class="metric-value" id="action">--</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Reward</span>
                        <span class="metric-value" id="reward">--</span>
                    </div>
                </div>

                <div class="card">
                    <h2>📊 Learning Progress</h2>
                    <div class="metric">
                        <span class="metric-label">Real Steps</span>
                        <span class="metric-value" id="real_steps">--</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Buffer Size</span>
                        <span class="metric-value" id="buffer_size">--</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">FQL Epsilon</span>
                        <span class="metric-value" id="fql_eps">--</span>
                    </div>
                </div>
            </div>
        </div>

        <div class="footer">
            <p>Aquaculture N3IWF Real Deployment | Last update: <span id="last-update">--</span></p>
        </div>
    </div>

    <script>
        function updateDashboard() {
            fetch('/api/state')
                .then(response => response.json())
                .then(data => {
                    if (data.error) {
                        document.getElementById('error-msg').style.display = 'block';
                        document.getElementById('content').style.display = 'none';
                        document.getElementById('status').textContent = 'System Not Running';
                        document.getElementById('status').className = 'status-connected disconnected';
                        return;
                    }

                    document.getElementById('error-msg').style.display = 'none';
                    document.getElementById('content').style.display = 'block';
                    document.getElementById('status').textContent = '✅ System Running';
                    document.getElementById('status').className = 'status-connected connected';

                    // Water quality
                    document.getElementById('pH').textContent = data.pH !== null ? data.pH.toFixed(3) : '--';
                    document.getElementById('temp').textContent = data.T !== null ? data.T.toFixed(1) + '°C' : '--';

                    // AI control
                    const phase = data.phase || '--';
                    let phaseClass = 'phase-rb';
                    if (phase === 'FQL') phaseClass = 'phase-fql';
                    else if (phase === 'DQN') phaseClass = 'phase-dqn';
                    document.getElementById('phase').innerHTML = `<span class="phase-badge ${phaseClass}">${phase}</span>`;
                    
                    document.getElementById('action').innerHTML = `<span class="action-badge">${data.action || '--'}</span>`;
                    document.getElementById('reward').textContent = data.reward !== null ? data.reward.toFixed(4) : '--';

                    // Learning progress
                    document.getElementById('real_steps').textContent = data.real_steps || '--';
                    document.getElementById('buffer_size').textContent = data.buffer_size || '--';
                    document.getElementById('fql_eps').textContent = data.fql_eps !== null ? data.fql_eps.toFixed(3) : '--';

                    // Last update
                    document.getElementById('last-update').textContent = new Date().toLocaleTimeString();
                })
                .catch(error => {
                    console.error('Error:', error);
                    document.getElementById('error-msg').style.display = 'block';
                    document.getElementById('content').style.display = 'none';
                    document.getElementById('status').textContent = 'Connection Error';
                    document.getElementById('status').className = 'status-connected disconnected';
                });
        }

        // Update every 2 seconds
        updateDashboard();
        setInterval(updateDashboard, 2000);
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/state')
def get_state():
    """Read state from state.json"""
    try:
        if not os.path.exists(STATE_JSON):
            return jsonify({
                "error": "state.json not found",
                "message": "Please start run_real.py first"
            })
        
        # Check if file is recent (updated in last 30 seconds)
        file_age = time.time() - os.path.getmtime(STATE_JSON)
        if file_age > 30:
            return jsonify({
                "error": "state.json is stale",
                "message": "System might not be running",
                "file_age": round(file_age, 1)
            })
        
        with open(STATE_JSON, 'r') as f:
            state = json.load(f)
        
        return jsonify(state)
    
    except Exception as e:
        return jsonify({
            "error": str(e),
            "message": "Failed to read state"
        })


@app.route('/api/stats')
def get_stats():
    """Get statistics from comparison.csv"""
    try:
        if not os.path.exists(COMPARISON_CSV):
            return jsonify({"error": "comparison.csv not found"})
        
        # Count lines (simple stats)
        with open(COMPARISON_CSV, 'r') as f:
            lines = f.readlines()
        
        return jsonify({
            "total_steps": len(lines) - 1,  # Minus header
            "csv_size": os.path.getsize(COMPARISON_CSV)
        })
    
    except Exception as e:
        return jsonify({"error": str(e)})


if __name__ == '__main__':
    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except Exception:
        local_ip = "0.0.0.0"
    
    print("\n" + "="*60)
    print("  Aquaculture Real Dashboard")
    print("="*60)
    print(f"  Dashboard  : http://{local_ip}:5000")
    print(f"  State file : {STATE_JSON}")
    print()
    print("  IMPORTANT:")
    print("  1. Start run_real.py first in another terminal")
    print("  2. Then access the dashboard")
    print("="*60 + "\n")
    
    app.run(host='0.0.0.0', port=5000, debug=False)
