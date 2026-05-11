import os
import json
import time
from collections import deque
from flask import Flask, render_template, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_REAL = os.path.join(BASE_DIR, "results", "hasil_real")
STATE_FILE = os.path.join(RESULTS_REAL, "state.json")

# In-memory rolling history — last 120 data points (~3 minutes at 1.5s interval)
_history = deque(maxlen=120)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/state')
def get_state():
    default = {
        "pH": None, "T": None, "action": "--",
        "phase": "WAITING", "buffer_size": 0,
        "reward": 0.0, "real_steps": 0, "fql_eps": 0.0,
        "timestamp": time.time()
    }
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                data = json.load(f)
            data["timestamp"] = time.time()
            _history.append(data)
            return jsonify(data)
    except Exception as e:
        print(f"Error reading state: {e}")
    return jsonify(default)


@app.route('/api/history')
def get_history():
    """Return rolling history buffer for chart initialization on page load."""
    return jsonify(list(_history))

if __name__ == '__main__':
    # Run on 0.0.0.0 to be accessible on local Wi-Fi / N3IWF Edge network
    app.run(host='0.0.0.0', port=5000, debug=False)
