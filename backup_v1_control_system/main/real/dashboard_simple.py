#!/usr/bin/env python3
"""
dashboard_simple.py - Simple Dashboard for Testing
===================================================
Minimal dashboard without Chart.js to test if browser can fetch API

Usage:
  python3 main/real/dashboard_simple.py
  Access: http://<IP>:5001
"""

import os
import sys
import json
import time
from flask import Flask, jsonify, render_template_string

# Path configuration
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESULTS_DIR = os.path.join(BASE_DIR, "results", "hasil_real")
STATE_JSON = os.path.join(RESULTS_DIR, "state.json")

os.makedirs(RESULTS_DIR, exist_ok=True)

app = Flask(__name__)

# Simple HTML without Chart.js
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Simple Dashboard Test</title>
    <meta charset="utf-8">
    <meta http-equiv="refresh" content="2">
    <style>
        body {
            font-family: monospace;
            background: #000;
            color: #0f0;
            padding: 20px;
            font-size: 16px;
        }
        .box {
            border: 2px solid #0f0;
            padding: 20px;
            margin: 20px 0;
        }
        .error { color: #f00; }
        .ok { color: #0f0; }
        .warn { color: #ff0; }
    </style>
</head>
<body>
    <h1>🐟 Simple Dashboard Test</h1>
    <p>Auto-refresh every 2 seconds (no JavaScript needed)</p>
    
    <div class="box">
        <h2>System Status</h2>
        <p>Time: {{ time }}</p>
        <p>Status: <span class="{{ status_class }}">{{ status }}</span></p>
    </div>
    
    <div class="box">
        <h2>Water Quality</h2>
        <p>pH: {{ pH }}</p>
        <p>Temperature: {{ T }} °C</p>
    </div>
    
    <div class="box">
        <h2>AI Control</h2>
        <p>Phase: {{ phase }}</p>
        <p>Action: {{ action }}</p>
        <p>Reward: {{ reward }}</p>
        <p>Real Steps: {{ real_steps }}</p>
    </div>
    
    <div class="box">
        <h2>Debug Info</h2>
        <p>state.json exists: {{ state_exists }}</p>
        <p>state.json age: {{ state_age }} seconds</p>
        <p>Raw data: {{ raw_data }}</p>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    """Render simple dashboard"""
    try:
        # Check if state.json exists
        state_exists = os.path.exists(STATE_JSON)
        
        if not state_exists:
            return render_template_string(HTML_TEMPLATE,
                time=time.strftime("%Y-%m-%d %H:%M:%S"),
                status="state.json not found",
                status_class="error",
                pH="--",
                T="--",
                phase="--",
                action="--",
                reward="--",
                real_steps="--",
                state_exists=False,
                state_age="N/A",
                raw_data="N/A"
            )
        
        # Check file age
        state_age = int(time.time() - os.path.getmtime(STATE_JSON))
        
        if state_age > 30:
            return render_template_string(HTML_TEMPLATE,
                time=time.strftime("%Y-%m-%d %H:%M:%S"),
                status=f"state.json is stale ({state_age}s old)",
                status_class="warn",
                pH="--",
                T="--",
                phase="--",
                action="--",
                reward="--",
                real_steps="--",
                state_exists=True,
                state_age=state_age,
                raw_data="File too old"
            )
        
        # Read state
        with open(STATE_JSON, 'r') as f:
            state = json.load(f)
        
        return render_template_string(HTML_TEMPLATE,
            time=time.strftime("%Y-%m-%d %H:%M:%S"),
            status="Online",
            status_class="ok",
            pH=state.get('pH', '--'),
            T=state.get('T', '--'),
            phase=state.get('phase', '--'),
            action=state.get('action', '--'),
            reward=state.get('reward', '--'),
            real_steps=state.get('real_steps', '--'),
            state_exists=True,
            state_age=state_age,
            raw_data=json.dumps(state, indent=2)
        )
    
    except Exception as e:
        return render_template_string(HTML_TEMPLATE,
            time=time.strftime("%Y-%m-%d %H:%M:%S"),
            status=f"Error: {str(e)}",
            status_class="error",
            pH="--",
            T="--",
            phase="--",
            action="--",
            reward="--",
            real_steps="--",
            state_exists="Error",
            state_age="Error",
            raw_data=str(e)
        )


if __name__ == '__main__':
    print("\n" + "="*70)
    print("  🐟 Simple Dashboard Test (No JavaScript)")
    print("="*70)
    print(f"  URL: http://10.42.0.1:5001")
    print(f"  Auto-refresh: Every 2 seconds (HTML meta refresh)")
    print(f"  No JavaScript required!")
    print("="*70 + "\n")
    
    app.run(host='0.0.0.0', port=5001, debug=False)
