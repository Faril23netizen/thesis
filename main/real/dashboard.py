#!/usr/bin/env python3
"""
dashboard.py - Professional Real-time Dashboard
================================================
Complete dashboard with charts and network monitoring

Usage:
  python3 main/real/dashboard.py
  Access: http://<IP>:5000
"""

import os
import sys
import json
import time
import socket
from flask import Flask, jsonify, render_template_string, make_response, request
from functools import wraps

# Path configuration
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESULTS_DIR = os.path.join(BASE_DIR, "results", "hasil_real")
NETWORK_DIR = os.path.join(BASE_DIR, "results", "network")
STATE_JSON = os.path.join(RESULTS_DIR, "state.json")
COMPARISON_CSV = os.path.join(RESULTS_DIR, "comparison.csv")
CALLBOX_STATS = os.path.join(NETWORK_DIR, "callbox_stats.json")
N3IWF_STATUS = os.path.join(NETWORK_DIR, "n3iwf_status.json")

# Ensure directories exist
os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(NETWORK_DIR, exist_ok=True)

app = Flask(__name__)

# CORS support - allow all origins
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

@app.after_request
def after_request(response):
    return add_cors_headers(response)

# HTML Template with Charts
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Aquaculture Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="refresh" content="2">
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #0f172a;
            color: #e2e8f0;
            padding: 20px;
        }
        .container { max-width: 1600px; margin: 0 auto; }
        
        /* Header */
        .header {
            background: linear-gradient(135deg, #1e40af 0%, #7c3aed 100%);
            border-radius: 16px;
            padding: 30px;
            margin-bottom: 24px;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3);
        }
        .header h1 {
            font-size: 2.5em;
            font-weight: 700;
            margin-bottom: 8px;
        }
        .header p {
            opacity: 0.9;
            font-size: 1.1em;
        }
        
        /* Status Bar */
        .status-bar {
            display: flex;
            gap: 16px;
            margin-bottom: 24px;
            flex-wrap: wrap;
        }
        .status-card {
            flex: 1;
            min-width: 200px;
            background: #1e293b;
            border-radius: 12px;
            padding: 20px;
            border: 1px solid #334155;
        }
        .status-label {
            font-size: 0.875em;
            color: #94a3b8;
            margin-bottom: 8px;
        }
        .status-value {
            font-size: 1.5em;
            font-weight: 700;
        }
        .status-online { color: #10b981; }
        .status-offline { color: #ef4444; }
        .status-warning { color: #f59e0b; }
        
        /* Grid Layout */
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 24px;
            margin-bottom: 24px;
        }
        .grid-full {
            grid-column: 1 / -1;
        }
        
        /* Card */
        .card {
            background: #1e293b;
            border-radius: 12px;
            padding: 24px;
            border: 1px solid #334155;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
        }
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        .card-title {
            font-size: 1.25em;
            font-weight: 600;
            color: #f1f5f9;
        }
        .card-badge {
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.875em;
            font-weight: 600;
        }
        .badge-success { background: #10b981; color: #fff; }
        .badge-danger { background: #ef4444; color: #fff; }
        .badge-warning { background: #f59e0b; color: #fff; }
        .badge-info { background: #3b82f6; color: #fff; }
        
        /* Metrics */
        .metrics {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 16px;
        }
        .metric {
            background: #0f172a;
            border-radius: 8px;
            padding: 16px;
            border: 1px solid #334155;
        }
        .metric-label {
            font-size: 0.875em;
            color: #94a3b8;
            margin-bottom: 8px;
        }
        .metric-value {
            font-size: 1.75em;
            font-weight: 700;
            color: #f1f5f9;
        }
        .metric-unit {
            font-size: 0.875em;
            color: #64748b;
            margin-left: 4px;
        }
        
        /* Chart Container */
        .chart-container {
            position: relative;
            height: 300px;
            margin-top: 16px;
        }
        
        /* Network Stats */
        .network-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 12px;
            margin-top: 16px;
        }
        .network-stat {
            background: #0f172a;
            border-radius: 8px;
            padding: 12px;
            text-align: center;
            border: 1px solid #334155;
        }
        .network-stat-label {
            font-size: 0.75em;
            color: #94a3b8;
            margin-bottom: 4px;
        }
        .network-stat-value {
            font-size: 1.25em;
            font-weight: 700;
        }
        
        /* Footer */
        .footer {
            text-align: center;
            margin-top: 32px;
            padding: 20px;
            color: #64748b;
            font-size: 0.875em;
        }
        
        /* Loading */
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .pulse { animation: pulse 2s infinite; }
        
        /* Error */
        .error-banner {
            background: #7f1d1d;
            border: 2px solid #ef4444;
            border-radius: 12px;
            padding: 24px;
            text-align: center;
            margin-bottom: 24px;
        }
        .error-banner h3 {
            margin-bottom: 12px;
            color: #fca5a5;
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <h1>🐟 Aquaculture Monitoring System</h1>
            <p>Real-time Water Quality & Network Performance Dashboard</p>
        </div>

        <!-- Error Banner -->
        <div id="error-banner" class="error-banner" style="{% if not has_data %}display: block;{% else %}display: none;{% endif %}">
            <h3>⚠️ System Not Running</h3>
            <p>Please start the system: <code>sudo ./start_all.sh</code></p>
        </div>

        <!-- Status Bar -->
        <div class="status-bar">
            <div class="status-card">
                <div class="status-label">System Status</div>
                <div class="status-value {% if has_data %}status-online{% else %}status-offline{% endif %}" id="system-status">{% if has_data %}Online{% else %}Connecting...{% endif %}</div>
            </div>
            <div class="status-card">
                <div class="status-label">IPsec Tunnel</div>
                <div class="status-value {% if ipsec_status == 'ESTABLISHED' %}status-online{% else %}status-offline{% endif %}" id="ipsec-status">{{ ipsec_status }}</div>
            </div>
            <div class="status-card">
                <div class="status-label">Pico 2W</div>
                <div class="status-value {% if has_data and pH != 'null' %}status-online{% else %}status-offline{% endif %}" id="pico-status">{% if has_data and pH != 'null' %}Connected{% else %}Disconnected{% endif %}</div>
            </div>
            <div class="status-card">
                <div class="status-label">AI Phase</div>
                <div class="status-value" id="ai-phase">{{ phase }}</div>
            </div>
        </div>

        <div id="main-content" style="{% if has_data %}display: block;{% else %}display: none;{% endif %}">
            <!-- Water Quality Section -->
            <div class="grid">
                <div class="card">
                    <div class="card-header">
                        <div class="card-title">💧 Water Quality</div>
                        <span class="card-badge badge-info" id="quality-badge">Monitoring</span>
                    </div>
                    <div class="metrics">
                        <div class="metric">
                            <div class="metric-label">pH Level</div>
                            <div class="metric-value" id="ph-value">{{ '%.3f'|format(pH) if pH != 'null' else '--' }}</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">Temperature</div>
                            <div class="metric-value">
                                <span id="temp-value">{{ '%.1f'|format(T) if T != 'null' else '--' }}</span>
                                <span class="metric-unit">°C</span>
                            </div>
                        </div>
                    </div>
                    <div class="chart-container">
                        <canvas id="waterChart"></canvas>
                    </div>
                </div>

                <div class="card">
                    <div class="card-header">
                        <div class="card-title">🤖 AI Control</div>
                        <span class="card-badge badge-success" id="ai-badge">Active</span>
                    </div>
                    <div class="metrics">
                        <div class="metric">
                            <div class="metric-label">Current Action</div>
                            <div class="metric-value" id="action-value">{{ action }}</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">Reward</div>
                            <div class="metric-value" id="reward-value">{{ '%.4f'|format(reward) if reward != 'null' else '--' }}</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">Real Steps</div>
                            <div class="metric-value" id="steps-value">{{ real_steps }}</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">Buffer Size</div>
                            <div class="metric-value" id="buffer-value">{{ buffer_size }}</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Network Performance Section -->
            <div class="grid">
                <div class="card grid-full">
                    <div class="card-header">
                        <div class="card-title">🌐 Network Performance (N3IWF + IPsec)</div>
                        <span class="card-badge badge-success" id="network-badge">Connected</span>
                    </div>
                    <div class="network-grid">
                        <div class="network-stat">
                            <div class="network-stat-label">Latency</div>
                            <div class="network-stat-value status-online" id="latency-value">{{ '%.1f'|format(avg_latency_ms) }} ms</div>
                        </div>
                        <div class="network-stat">
                            <div class="network-stat-label">Packet Loss</div>
                            <div class="network-stat-value" id="packet-loss-value">{{ '%.2f'|format(packet_loss_rate) }} %</div>
                        </div>
                        <div class="network-stat">
                            <div class="network-stat-label">Throughput</div>
                            <div class="network-stat-value" id="throughput-value">{{ throughput }} Mbps</div>
                        </div>
                        <div class="network-stat">
                            <div class="network-stat-label">Packets Sent</div>
                            <div class="network-stat-value" id="packets-sent-value">{{ '{:,}'.format(packets_sent) }}</div>
                        </div>
                        <div class="network-stat">
                            <div class="network-stat-label">Packets Dropped</div>
                            <div class="network-stat-value" id="packets-dropped-value">{{ '{:,}'.format(packets_dropped) }}</div>
                        </div>
                        <div class="network-stat">
                            <div class="network-stat-label">Uptime</div>
                            <div class="network-stat-value" id="uptime-value">{{ '%.1f'|format(uptime) }} h</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 5G Core Status -->
            <div class="grid">
                <div class="card">
                    <div class="card-header">
                        <div class="card-title">📡 5G Core Components</div>
                    </div>
                    <div class="metrics">
                        <div class="metric">
                            <div class="metric-label">AMF (Access)</div>
                            <div class="metric-value status-online" id="amf-status">{{ amf_status }}</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">SMF (Session)</div>
                            <div class="metric-value status-online" id="smf-status">{{ smf_status }}</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">UPF (User Plane)</div>
                            <div class="metric-value status-online" id="upf-status">{{ upf_status }}</div>
                        </div>
                    </div>
                </div>

                <div class="card">
                    <div class="card-header">
                        <div class="card-title">📊 Learning Progress</div>
                    </div>
                    <div class="metrics">
                        <div class="metric">
                            <div class="metric-label">FQL Epsilon</div>
                            <div class="metric-value" id="epsilon-value">{{ '%.3f'|format(fql_eps) if fql_eps != 'null' else '--' }}</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">Total Energy</div>
                            <div class="metric-value" id="energy-value">--</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Footer -->
        <div class="footer">
            <p>Aquaculture Edge AI with N3IWF Integration | Last update: <span id="last-update">--</span></p>
        </div>
    </div>

    <script>
        // Chart.js configuration
        const chartConfig = {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'pH',
                    data: [],
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    tension: 0.4,
                    yAxisID: 'y'
                }, {
                    label: 'Temperature (°C)',
                    data: [],
                    borderColor: '#ef4444',
                    backgroundColor: 'rgba(239, 68, 68, 0.1)',
                    tension: 0.4,
                    yAxisID: 'y1'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false,
                },
                plugins: {
                    legend: {
                        labels: { color: '#e2e8f0' }
                    }
                },
                scales: {
                    x: {
                        ticks: { color: '#94a3b8' },
                        grid: { color: '#334155' }
                    },
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        ticks: { color: '#3b82f6' },
                        grid: { color: '#334155' },
                        title: {
                            display: true,
                            text: 'pH',
                            color: '#3b82f6'
                        }
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        ticks: { color: '#ef4444' },
                        grid: { display: false },
                        title: {
                            display: true,
                            text: 'Temperature (°C)',
                            color: '#ef4444'
                        }
                    }
                }
            }
        };

        const maxDataPoints = 50;

        // Dashboard uses server-side rendering with auto-refresh every 2s
        // Chart.js renders pH & Temperature (data resets on each page refresh)
        const ctx = document.getElementById('waterChart').getContext('2d');
        const waterChart = new Chart(ctx, chartConfig);
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    """Render dashboard with server-side data"""
    try:
        # Read state.json
        state = {}
        if os.path.exists(STATE_JSON):
            file_age = time.time() - os.path.getmtime(STATE_JSON)
            if file_age < 30:
                with open(STATE_JSON, 'r') as f:
                    state = json.load(f)
        
        # Read network stats
        network = {}
        if os.path.exists(CALLBOX_STATS):
            with open(CALLBOX_STATS, 'r') as f:
                network = json.load(f)
        
        # Calculate packet loss rate
        packets_sent = network.get('packets_sent', 0)
        packets_dropped = network.get('packets_dropped', 0)
        packet_loss_rate = (packets_dropped / max(packets_sent, 1)) * 100 if packets_sent > 0 else 0
        
        # Prepare data for template
        template_data = {
            'pH': state.get('pH', 'null'),
            'T': state.get('T', 'null'),
            'action': state.get('action', '--'),
            'phase': state.get('phase', '--'),
            'reward': state.get('reward', 'null'),
            'real_steps': state.get('real_steps', '--'),
            'buffer_size': state.get('buffer_size', '--'),
            'fql_eps': state.get('fql_eps', 'null'),
            'ipsec_status': network.get('ipsec_status', 'UNKNOWN'),
            'avg_latency_ms': network.get('avg_latency_ms', 0),
            'packet_loss_rate': packet_loss_rate,
            'throughput': network.get('current_bandwidth_mbps', 0),
            'packets_sent': packets_sent,
            'packets_dropped': packets_dropped,
            'uptime': network.get('uptime', 0) / 3600 if network.get('uptime', 0) > 0 else 0,
            'amf_status': network.get('amf_status', 'UNKNOWN'),
            'smf_status': network.get('smf_status', 'UNKNOWN'),
            'upf_status': network.get('upf_status', 'UNKNOWN'),
            'has_data': bool(state)
        }
        
        return render_template_string(HTML_TEMPLATE, **template_data)
    
    except Exception as e:
        print(f"[ERROR] Error rendering dashboard: {e}")
        return render_template_string(HTML_TEMPLATE, 
            pH='null', T='null', action='--', phase='--', 
            reward='null', real_steps='--', buffer_size='--', 
            fql_eps='null', ipsec_status='UNKNOWN', 
            avg_latency_ms=0, packet_loss_rate=0, throughput=0,
            packets_sent=0, packets_dropped=0, uptime=0,
            amf_status='UNKNOWN', smf_status='UNKNOWN', upf_status='UNKNOWN',
            has_data=False)


@app.route('/api/state')
def get_state():
    """Read state from state.json"""
    try:
        print(f"[API] /api/state called from {request.remote_addr if 'request' in dir() else 'unknown'}")
        
        if not os.path.exists(STATE_JSON):
            print(f"[API] state.json not found at {STATE_JSON}")
            return jsonify({"error": "state.json not found"})
        
        file_age = time.time() - os.path.getmtime(STATE_JSON)
        if file_age > 30:
            print(f"[API] state.json is stale (age: {file_age}s)")
            return jsonify({"error": "state.json is stale"})
        
        with open(STATE_JSON, 'r') as f:
            state = json.load(f)
        
        print(f"[API] Returning state: pH={state.get('pH')}, T={state.get('T')}")
        return jsonify(state)
    
    except Exception as e:
        print(f"[API] Error in /api/state: {e}")
        return jsonify({"error": str(e)})


@app.route('/api/network')
def get_network():
    """Read network stats from callbox_stats.json"""
    try:
        # Check if file exists and is recent
        if not os.path.exists(CALLBOX_STATS):
            return jsonify({
                "error": "Network stats not available yet",
                "ipsec_status": "UNKNOWN",
                "avg_latency_ms": 0,
                "packet_loss_rate": 0,
                "throughput": 0,
                "packets_sent": 0,
                "packets_dropped": 0,
                "uptime": 0,
                "amf_status": "UNKNOWN",
                "smf_status": "UNKNOWN",
                "upf_status": "UNKNOWN"
            })
        
        # Check if file is stale (older than 30 seconds)
        file_age = time.time() - os.path.getmtime(CALLBOX_STATS)
        if file_age > 30:
            return jsonify({
                "error": "Network stats are stale",
                "ipsec_status": "STALE",
                "avg_latency_ms": 0,
                "packet_loss_rate": 0,
                "throughput": 0,
                "packets_sent": 0,
                "packets_dropped": 0,
                "uptime": 0,
                "amf_status": "UNKNOWN",
                "smf_status": "UNKNOWN",
                "upf_status": "UNKNOWN"
            })
        
        with open(CALLBOX_STATS, 'r') as f:
            stats = json.load(f)
        
        # Calculate packet loss rate
        packets_sent = stats.get('packets_sent', 0)
        packets_dropped = stats.get('packets_dropped', 0)
        packet_loss_rate = (packets_dropped / max(packets_sent, 1)) * 100 if packets_sent > 0 else 0
        
        return jsonify({
            "ipsec_status": stats.get('ipsec_status', 'UNKNOWN'),
            "avg_latency_ms": stats.get('avg_latency_ms', 0),
            "packet_loss_rate": packet_loss_rate,
            "throughput": stats.get('current_bandwidth_mbps', 0),
            "packets_sent": packets_sent,
            "packets_dropped": packets_dropped,
            "uptime": stats.get('uptime', 0),
            "amf_status": stats.get('amf_status', 'UNKNOWN'),
            "smf_status": stats.get('smf_status', 'UNKNOWN'),
            "upf_status": stats.get('upf_status', 'UNKNOWN')
        })
    
    except json.JSONDecodeError:
        return jsonify({
            "error": "Invalid network stats format",
            "ipsec_status": "ERROR",
            "avg_latency_ms": 0,
            "packet_loss_rate": 0,
            "throughput": 0,
            "packets_sent": 0,
            "packets_dropped": 0,
            "uptime": 0,
            "amf_status": "ERROR",
            "smf_status": "ERROR",
            "upf_status": "ERROR"
        })
    except Exception as e:
        return jsonify({
            "error": str(e),
            "ipsec_status": "ERROR",
            "avg_latency_ms": 0,
            "packet_loss_rate": 0,
            "throughput": 0,
            "packets_sent": 0,
            "packets_dropped": 0,
            "uptime": 0,
            "amf_status": "ERROR",
            "smf_status": "ERROR",
            "upf_status": "ERROR"
        })


if __name__ == '__main__':
    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except Exception:
        local_ip = "0.0.0.0"
    
    print("\n" + "="*70)
    print("  🐟 Aquaculture Professional Dashboard")
    print("="*70)
    print(f"  Dashboard  : http://{local_ip}:8080")
    print(f"  Features   : Real-time charts, Network monitoring, 5G Core status")
    print()
    print("  Make sure system is running: sudo ./start_all.sh")
    print("="*70 + "\n")
    
    app.run(host='0.0.0.0', port=8080, debug=False)
