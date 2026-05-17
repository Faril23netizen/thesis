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
from flask import Flask, jsonify, render_template_string

# Path configuration
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESULTS_DIR = os.path.join(BASE_DIR, "results", "hasil_real")
NETWORK_DIR = os.path.join(BASE_DIR, "results", "network")
STATE_JSON = os.path.join(RESULTS_DIR, "state.json")
COMPARISON_CSV = os.path.join(RESULTS_DIR, "comparison.csv")
CALLBOX_STATS = os.path.join(NETWORK_DIR, "callbox_stats.json")
N3IWF_STATUS = os.path.join(NETWORK_DIR, "n3iwf_status.json")

app = Flask(__name__)

# HTML Template with Charts
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Aquaculture Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
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
        <div id="error-banner" class="error-banner" style="display: none;">
            <h3>⚠️ System Not Running</h3>
            <p>Please start the system: <code>sudo ./start_all.sh</code></p>
        </div>

        <!-- Status Bar -->
        <div class="status-bar">
            <div class="status-card">
                <div class="status-label">System Status</div>
                <div class="status-value status-offline pulse" id="system-status">Connecting...</div>
            </div>
            <div class="status-card">
                <div class="status-label">IPsec Tunnel</div>
                <div class="status-value status-offline" id="ipsec-status">Unknown</div>
            </div>
            <div class="status-card">
                <div class="status-label">Pico 2W</div>
                <div class="status-value status-offline" id="pico-status">Disconnected</div>
            </div>
            <div class="status-card">
                <div class="status-label">AI Phase</div>
                <div class="status-value" id="ai-phase">--</div>
            </div>
        </div>

        <div id="main-content" style="display: none;">
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
                            <div class="metric-value" id="ph-value">--</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">Temperature</div>
                            <div class="metric-value">
                                <span id="temp-value">--</span>
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
                            <div class="metric-value" id="action-value">--</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">Reward</div>
                            <div class="metric-value" id="reward-value">--</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">Real Steps</div>
                            <div class="metric-value" id="steps-value">--</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">Buffer Size</div>
                            <div class="metric-value" id="buffer-value">--</div>
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
                            <div class="network-stat-value status-online" id="latency-value">-- ms</div>
                        </div>
                        <div class="network-stat">
                            <div class="network-stat-label">Packet Loss</div>
                            <div class="network-stat-value" id="packet-loss-value">-- %</div>
                        </div>
                        <div class="network-stat">
                            <div class="network-stat-label">Throughput</div>
                            <div class="network-stat-value" id="throughput-value">-- Mbps</div>
                        </div>
                        <div class="network-stat">
                            <div class="network-stat-label">Packets Sent</div>
                            <div class="network-stat-value" id="packets-sent-value">--</div>
                        </div>
                        <div class="network-stat">
                            <div class="network-stat-label">Packets Dropped</div>
                            <div class="network-stat-value" id="packets-dropped-value">--</div>
                        </div>
                        <div class="network-stat">
                            <div class="network-stat-label">Uptime</div>
                            <div class="network-stat-value" id="uptime-value">-- h</div>
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
                            <div class="metric-value status-online" id="amf-status">--</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">SMF (Session)</div>
                            <div class="metric-value status-online" id="smf-status">--</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">UPF (User Plane)</div>
                            <div class="metric-value status-online" id="upf-status">--</div>
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
                            <div class="metric-value" id="epsilon-value">--</div>
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

        const ctx = document.getElementById('waterChart').getContext('2d');
        const waterChart = new Chart(ctx, chartConfig);

        const maxDataPoints = 50;

        function updateDashboard() {
            Promise.all([
                fetch('/api/state').then(r => r.json()),
                fetch('/api/network').then(r => r.json())
            ]).then(([state, network]) => {
                if (state.error) {
                    document.getElementById('error-banner').style.display = 'block';
                    document.getElementById('main-content').style.display = 'none';
                    document.getElementById('system-status').textContent = 'Offline';
                    document.getElementById('system-status').className = 'status-value status-offline';
                    return;
                }

                document.getElementById('error-banner').style.display = 'none';
                document.getElementById('main-content').style.display = 'block';
                document.getElementById('system-status').textContent = 'Online';
                document.getElementById('system-status').className = 'status-value status-online';

                // Water quality
                const pH = state.pH !== null ? state.pH.toFixed(3) : '--';
                const temp = state.T !== null ? state.T.toFixed(1) : '--';
                document.getElementById('ph-value').textContent = pH;
                document.getElementById('temp-value').textContent = temp;

                // Update chart
                if (state.pH !== null && state.T !== null) {
                    const now = new Date().toLocaleTimeString();
                    waterChart.data.labels.push(now);
                    waterChart.data.datasets[0].data.push(state.pH);
                    waterChart.data.datasets[1].data.push(state.T);

                    if (waterChart.data.labels.length > maxDataPoints) {
                        waterChart.data.labels.shift();
                        waterChart.data.datasets[0].data.shift();
                        waterChart.data.datasets[1].data.shift();
                    }
                    waterChart.update('none');
                }

                // AI control
                const phase = state.phase || '--';
                document.getElementById('ai-phase').textContent = phase;
                document.getElementById('action-value').textContent = state.action || '--';
                document.getElementById('reward-value').textContent = state.reward !== null ? state.reward.toFixed(4) : '--';
                document.getElementById('steps-value').textContent = state.real_steps || '--';
                document.getElementById('buffer-value').textContent = state.buffer_size || '--';
                document.getElementById('epsilon-value').textContent = state.fql_eps !== null ? state.fql_eps.toFixed(3) : '--';

                // Network stats
                if (!network.error) {
                    const ipsecStatus = network.ipsec_status || 'UNKNOWN';
                    document.getElementById('ipsec-status').textContent = ipsecStatus;
                    document.getElementById('ipsec-status').className = ipsecStatus === 'ESTABLISHED' ? 
                        'status-value status-online' : 'status-value status-offline';

                    document.getElementById('latency-value').textContent = 
                        network.avg_latency_ms ? network.avg_latency_ms.toFixed(1) + ' ms' : '-- ms';
                    
                    const packetLoss = network.packet_loss_rate ? network.packet_loss_rate.toFixed(2) : '--';
                    document.getElementById('packet-loss-value').textContent = packetLoss + ' %';
                    
                    document.getElementById('throughput-value').textContent = 
                        network.throughput ? network.throughput + ' Mbps' : '-- Mbps';
                    
                    document.getElementById('packets-sent-value').textContent = 
                        network.packets_sent ? network.packets_sent.toLocaleString() : '--';
                    
                    document.getElementById('packets-dropped-value').textContent = 
                        network.packets_dropped ? network.packets_dropped.toLocaleString() : '--';
                    
                    const uptime = network.uptime ? (network.uptime / 3600).toFixed(1) : '--';
                    document.getElementById('uptime-value').textContent = uptime + ' h';

                    // 5G Core
                    document.getElementById('amf-status').textContent = network.amf_status || '--';
                    document.getElementById('smf-status').textContent = network.smf_status || '--';
                    document.getElementById('upf-status').textContent = network.upf_status || '--';
                }

                // Pico status
                document.getElementById('pico-status').textContent = state.pH !== null ? 'Connected' : 'Waiting';
                document.getElementById('pico-status').className = state.pH !== null ? 
                    'status-value status-online' : 'status-value status-warning';

                // Last update
                document.getElementById('last-update').textContent = new Date().toLocaleTimeString();
            }).catch(error => {
                console.error('Error:', error);
                document.getElementById('error-banner').style.display = 'block';
                document.getElementById('main-content').style.display = 'none';
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
            return jsonify({"error": "state.json not found"})
        
        file_age = time.time() - os.path.getmtime(STATE_JSON)
        if file_age > 30:
            return jsonify({"error": "state.json is stale"})
        
        with open(STATE_JSON, 'r') as f:
            state = json.load(f)
        
        return jsonify(state)
    
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/network')
def get_network():
    """Read network stats from callbox_stats.json"""
    try:
        if not os.path.exists(CALLBOX_STATS):
            return jsonify({"error": "callbox_stats.json not found"})
        
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
    
    except Exception as e:
        return jsonify({"error": str(e)})


if __name__ == '__main__':
    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except Exception:
        local_ip = "0.0.0.0"
    
    print("\n" + "="*70)
    print("  🐟 Aquaculture Professional Dashboard")
    print("="*70)
    print(f"  Dashboard  : http://{local_ip}:5000")
    print(f"  Features   : Real-time charts, Network monitoring, 5G Core status")
    print()
    print("  Make sure system is running: sudo ./start_all.sh")
    print("="*70 + "\n")
    
    app.run(host='0.0.0.0', port=5000, debug=False)
