from flask import Flask, render_template_string, Response, jsonify
import subprocess
import threading
import os
import signal
import psutil
from database.operations import get_current_inventory

app = Flask(__name__)

# Track running processes
processes = {
    'light_capture': None,
    'live_feed': None
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Fridge-Sight Control Panel</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 20px auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .control-panel {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .button {
            padding: 10px 20px;
            margin: 5px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
        }
        .start {
            background-color: #4CAF50;
            color: white;
        }
        .stop {
            background-color: #f44336;
            color: white;
        }
        .status {
            margin: 10px 0;
            padding: 10px;
            border-radius: 4px;
        }
        .running {
            background-color: #e8f5e9;
            color: #2e7d32;
        }
        .stopped {
            background-color: #ffebee;
            color: #c62828;
        }
        #live-feed {
            margin-top: 20px;
            max-width: 100%;
            height: auto;
        }
    </style>
    <script>
        function updateStatus() {
            fetch('/status')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('light-capture-status').textContent = 
                        data.light_capture ? 'Running' : 'Stopped';
                    document.getElementById('light-capture-status').className = 
                        'status ' + (data.light_capture ? 'running' : 'stopped');
                    
                    document.getElementById('live-feed-status').textContent = 
                        data.live_feed ? 'Running' : 'Stopped';
                    document.getElementById('live-feed-status').className = 
                        'status ' + (data.live_feed ? 'running' : 'stopped');
                    
                    // Show/hide live feed
                    const feedFrame = document.getElementById('live-feed');
                    feedFrame.style.display = data.live_feed ? 'block' : 'none';
                });
        }

        function controlService(service, action) {
            fetch(`/control/${service}/${action}`)
                .then(response => response.json())
                .then(data => {
                    updateStatus();
                });
        }

        // Update status every 5 seconds
        setInterval(updateStatus, 5000);
        // Initial status update
        document.addEventListener('DOMContentLoaded', updateStatus);
    </script>
</head>
<body>
    <div class="control-panel">
        <h1>Fridge-Sight Control Panel</h1>
        
        <h2>Light Capture & Identify</h2>
        <div id="light-capture-status" class="status">Checking...</div>
        <button class="button start" onclick="controlService('light_capture', 'start')">Start</button>
        <button class="button stop" onclick="controlService('light_capture', 'stop')">Stop</button>
        
        <h2>Live Feed</h2>
        <div id="live-feed-status" class="status">Checking...</div>
        <button class="button start" onclick="controlService('live_feed', 'start')">Start</button>
        <button class="button stop" onclick="controlService('live_feed', 'stop')">Stop</button>
        
        <img id="live-feed" src="http://localhost:5000/video_feed" style="display: none;">
        
        <h2>Current Inventory</h2>
        <div id="inventory-container" class="status">Loading...</div>
        <button class="button" onclick="refreshInventory()">Refresh Inventory</button>
        
        <script>
            function refreshInventory() {
                fetch('/inventory')
                    .then(response => response.json())
                    .then(data => {
                        const container = document.getElementById('inventory-container');
                        if (data.length === 0) {
                            container.innerHTML = '<p>No items in inventory</p>';
                            return;
                        }
                        
                        const table = `
                            <table style="width:100%; border-collapse: collapse; margin-top: 10px;">
                                <thead>
                                    <tr style="background-color: #f5f5f5;">
                                        <th style="padding: 8px; border: 1px solid #ddd;">Item</th>
                                        <th style="padding: 8px; border: 1px solid #ddd;">Quantity</th>
                                        <th style="padding: 8px; border: 1px solid #ddd;">Last Seen</th>
                                        <th style="padding: 8px; border: 1px solid #ddd;">Confidence</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${data.map(item => `
                                        <tr>
                                            <td style="padding: 8px; border: 1px solid #ddd;">${item.name}</td>
                                            <td style="padding: 8px; border: 1px solid #ddd;">${item.quantity}</td>
                                            <td style="padding: 8px; border: 1px solid #ddd;">${new Date(item.last_seen).toLocaleString()}</td>
                                            <td style="padding: 8px; border: 1px solid #ddd;">${(item.confidence * 100).toFixed(1)}%</td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>`;
                        container.innerHTML = table;
                    })
                    .catch(error => {
                        console.error('Error fetching inventory:', error);
                        document.getElementById('inventory-container').innerHTML = 
                            '<p style="color: red;">Error loading inventory</p>';
                    });
            }
            
            // Initial inventory load
            document.addEventListener('DOMContentLoaded', refreshInventory);
            // Refresh inventory every 30 seconds
            setInterval(refreshInventory, 30000);
        </script>
    </div>
</body>
</html>
"""

def is_process_running(pid):
    try:
        return psutil.pid_exists(pid)
    except:
        return False

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/status')
def status():
    return jsonify({
        'light_capture': processes['light_capture'] is not None and 
                        is_process_running(processes['light_capture'].pid),
        'live_feed': processes['live_feed'] is not None and 
                    is_process_running(processes['live_feed'].pid)
    })

@app.route('/control/<service>/<action>')
def control(service, action):
    if service not in processes:
        return jsonify({'error': 'Invalid service'}), 400
    
    if action == 'start':
        if processes[service] is None or not is_process_running(processes[service].pid):
            script = 'light_capture_identify.py' if service == 'light_capture' else 'live_feed.py'
            processes[service] = subprocess.Popen(['python3', script])
            
    elif action == 'stop':
        if processes[service] and is_process_running(processes[service].pid):
            os.kill(processes[service].pid, signal.SIGTERM)
            processes[service] = None
    
    return jsonify({'status': 'success'})

@app.route('/inventory')
def inventory():
    try:
        items = get_current_inventory()
        return jsonify(items)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def cleanup():
    for process in processes.values():
        if process and is_process_running(process.pid):
            os.kill(process.pid, signal.SIGTERM)

if __name__ == '__main__':
    # Register cleanup handler
    import atexit
    atexit.register(cleanup)
    
    # Run the control panel on port 8000 (since live_feed uses 5000)
    app.run(host='0.0.0.0', port=8000, threaded=True) 