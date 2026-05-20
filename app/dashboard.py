import os
import json
import logging
from collections import deque
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# A valid minimal PDF that renders "TEST DIAGNOSTIC PRINT" text
TEST_PDF_BYTES = (
    b'%PDF-1.4\n'
    b'1 0 obj <</Type/Catalog/Pages 2 0 R>> endobj\n'
    b'2 0 obj <</Type/Pages/Kids[3 0 R]/Count 1>> endobj\n'
    b'3 0 obj <</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>> endobj\n'
    b'4 0 obj <</Type/Font/Subtype/Type1/BaseFont/Helvetica>> endobj\n'
    b'5 0 obj <</Length 49>> stream\n'
    b'BT\n/F1 24 Tf\n100 700 Td\n(TEST DIAGNOSTIC PRINT) Tj\nET\n'
    b'endstream\n'
    b'endobj\n'
    b'xref\n'
    b'0 6\n'
    b'0000000000 65535 f \n'
    b'0000000009 00000 n \n'
    b'0000000056 00000 n \n'
    b'0000000111 00000 n \n'
    b'0000000223 00000 n \n'
    b'0000000295 00000 n \n'
    b'trailer <</Size 6/Root 1 0 R>>\n'
    b'startxref\n'
    b'390\n'
    b'%%EOF\n'
)

# Shared Dashboard State
class DashboardState:
    station_id = "PACK_STATION_01"
    api_base_url = "http://127.0.0.1:8000/api/v1/print"
    poll_interval = 5
    history = []  # list of dicts: {job_id, status, timestamp, error}
    logs_queue = deque(maxlen=100)

    @classmethod
    def add_job(cls, job_id, status, error=None):
        cls.history.insert(0, {
            "job_id": job_id,
            "status": status,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error": error
        })

# Custom logging handler to pipe gateway logs to the dashboard in-memory queue
class MemoryLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] - %(message)s"))

    def emit(self, record):
        try:
            msg = self.format(record)
            DashboardState.logs_queue.append(msg)
        except Exception:
            self.handleError(record)

# Setup memory logging handler
memory_log_handler = MemoryLogHandler()
logger = logging.getLogger("SimplePrintGateway")
logger.addHandler(memory_log_handler)

# The HTML dashboard content
INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Print Gateway Console</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0b0f19;
            --card-bg: rgba(17, 24, 39, 0.7);
            --card-border: rgba(255, 255, 255, 0.06);
            --text-main: #f3f4f6;
            --text-muted: #9ca3af;
            --primary: #3b82f6;
            --primary-glow: rgba(59, 130, 246, 0.2);
            --success: #10b981;
            --success-glow: rgba(16, 185, 129, 0.2);
            --danger: #ef4444;
            --danger-glow: rgba(239, 68, 68, 0.2);
            --warning: #f59e0b;
            --warning-glow: rgba(245, 158, 11, 0.2);
            --console-bg: #030712;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Outfit', sans-serif;
            background-color: var(--bg-color);
            background-image: radial-gradient(circle at 50% -20%, #1e293b, var(--bg-color));
            color: var(--text-main);
            min-height: 100vh;
            padding: 2rem;
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--card-border);
            padding-bottom: 1.5rem;
        }

        .logo-section {
            display: flex;
            align-items: center;
            gap: 1rem;
        }

        .logo-icon {
            background: linear-gradient(135deg, var(--primary), #8b5cf6);
            width: 42px;
            height: 42px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 1.25rem;
            box-shadow: 0 4px 20px var(--primary-glow);
        }

        h1 {
            font-size: 1.5rem;
            font-weight: 600;
            background: linear-gradient(to right, #ffffff, #9ca3af);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .status-badge {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            background: var(--success-glow);
            border: 1px solid rgba(16, 185, 129, 0.3);
            color: var(--success);
            padding: 0.35rem 0.85rem;
            border-radius: 9999px;
            font-size: 0.85rem;
            font-weight: 500;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            box-shadow: 0 0 15px rgba(16, 185, 129, 0.1);
        }

        .status-dot {
            width: 8px;
            height: 8px;
            background-color: var(--success);
            border-radius: 50%;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0% { transform: scale(0.9); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
            100% { transform: scale(0.9); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 1.5rem;
        }

        .card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 1.5rem;
            backdrop-filter: blur(12px);
            display: flex;
            flex-direction: column;
            gap: 1rem;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            transition: transform 0.2s, border-color 0.2s;
        }

        .card:hover {
            border-color: rgba(255,255,255,0.1);
        }

        .card-title {
            font-size: 0.9rem;
            font-weight: 500;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .card-value {
            font-size: 1.75rem;
            font-weight: 700;
        }

        .card-meta {
            font-size: 0.85rem;
            color: var(--text-muted);
        }

        .btn {
            background: var(--primary);
            color: white;
            border: none;
            padding: 0.75rem 1.2rem;
            border-radius: 10px;
            font-weight: 500;
            font-family: inherit;
            cursor: pointer;
            transition: all 0.2s;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
            box-shadow: 0 4px 15px var(--primary-glow);
        }

        .btn:hover {
            background: #2563eb;
            transform: translateY(-1px);
        }

        .btn:active {
            transform: translateY(1px);
        }

        .btn-outline {
            background: transparent;
            border: 1px solid var(--card-border);
            color: var(--text-main);
            box-shadow: none;
        }

        .btn-outline:hover {
            background: rgba(255,255,255,0.05);
            border-color: rgba(255,255,255,0.2);
        }

        /* Console styling */
        .console-section {
            display: grid;
            grid-template-columns: 3fr 2fr;
            gap: 1.5rem;
        }

        .console-container {
            background: var(--console-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 1.25rem;
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
            height: 380px;
        }

        .console-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            padding-bottom: 0.5rem;
        }

        .console-title {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem;
            color: var(--primary);
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .console-body {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.8rem;
            color: #10b981;
            overflow-y: auto;
            flex-grow: 1;
            display: flex;
            flex-direction: column;
            gap: 0.35rem;
            scrollbar-width: thin;
        }

        /* History Table */
        .history-container {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 1.25rem;
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
            height: 380px;
        }

        .history-body {
            overflow-y: auto;
            flex-grow: 1;
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }

        .history-item {
            background: rgba(255,255,255,0.02);
            border: 1px solid rgba(255,255,255,0.04);
            border-radius: 8px;
            padding: 0.65rem 0.85rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.85rem;
        }

        .item-info {
            display: flex;
            flex-direction: column;
            gap: 0.2rem;
        }

        .item-id {
            font-family: 'JetBrains Mono', monospace;
            font-weight: 500;
        }

        .item-time {
            font-size: 0.75rem;
            color: var(--text-muted);
        }

        .badge {
            padding: 0.25rem 0.6rem;
            border-radius: 6px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.02em;
        }

        .badge-success {
            background: var(--success-glow);
            color: var(--success);
            border: 1px solid rgba(16, 185, 129, 0.2);
        }

        .badge-failed {
            background: var(--danger-glow);
            color: var(--danger);
            border: 1px solid rgba(239, 68, 68, 0.2);
        }
        
        .badge-pending {
            background: var(--warning-glow);
            color: var(--warning);
            border: 1px solid rgba(245, 158, 11, 0.2);
        }

        /* Custom scrollbar */
        ::-webkit-scrollbar {
            width: 6px;
        }
        ::-webkit-scrollbar-track {
            background: transparent;
        }
        ::-webkit-scrollbar-thumb {
            background: rgba(255,255,255,0.1);
            border-radius: 10px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: rgba(255,255,255,0.2);
        }
    </style>
</head>
<body>
    <header>
        <div class="logo-section">
            <div class="logo-icon">🖨️</div>
            <div>
                <h1>Print Gateway Monitor</h1>
                <div class="card-meta" style="margin-top: 0.1rem;">Local Control Dashboard</div>
            </div>
        </div>
        <div class="status-badge" id="global-status">
            <div class="status-dot"></div>
            <span id="status-text">Polling Active</span>
        </div>
    </header>

    <div class="grid">
        <div class="card">
            <div class="card-title">Station Configuration</div>
            <div class="card-value" id="station-id" style="font-size: 1.4rem; font-family: 'JetBrains Mono', monospace; color: var(--primary);">--</div>
            <div class="card-meta" id="station-url">Endpoint: --</div>
        </div>
        <div class="card">
            <div class="card-title">Print Productivity</div>
            <div class="card-value" id="print-stats">0 / 0</div>
            <div class="card-meta" id="success-rate">Success Rate: 100%</div>
        </div>
        <div class="card" style="justify-content: space-between;">
            <div>
                <div class="card-title">Diagnostic Controls</div>
                <div class="card-meta" style="margin-top: 0.25rem;">Trigger loopbacks or run test pages instantly.</div>
            </div>
            <div style="display: flex; gap: 0.5rem;">
                <button class="btn" style="flex: 1;" onclick="triggerTestPrint()">
                    ⚡ Print Test Page
                </button>
            </div>
        </div>
    </div>

    <div class="console-section">
        <div class="console-container">
            <div class="console-header">
                <div class="console-title">🖥️ LIVE LOG CONSOLE</div>
                <div class="card-meta">Auto-scroll enabled</div>
            </div>
            <div class="console-body" id="console-logs">
                <!-- Logs will be loaded dynamically -->
            </div>
        </div>

        <div class="history-container">
            <div class="console-header">
                <div class="console-title" style="color: var(--success);">📋 JOB HISTORY</div>
                <div class="card-meta" id="history-count">0 jobs processed</div>
            </div>
            <div class="history-body" id="history-list">
                <!-- Job history will be loaded dynamically -->
            </div>
        </div>
    </div>

    <script>
        // Update function
        async function fetchStatus() {
            try {
                const response = await fetch('/api/status');
                const data = await response.json();

                // 1. Update config card
                document.getElementById('station-id').textContent = data.station_id;
                document.getElementById('station-url').textContent = 'Endpoint: ' + data.api_base_url;

                // 2. Update stats card
                const total = data.history.length;
                const succeeded = data.history.filter(j => j.status === 'COMPLETED').length;
                document.getElementById('print-stats').textContent = `${succeeded} / ${total}`;
                
                const rate = total > 0 ? Math.round((succeeded / total) * 100) : 100;
                document.getElementById('success-rate').textContent = `Success Rate: ${rate}%`;

                // 3. Update history list
                const historyList = document.getElementById('history-list');
                document.getElementById('history-count').textContent = `${total} job${total === 1 ? '' : 's'} processed`;
                
                if (total === 0) {
                    historyList.innerHTML = '<div class="card-meta" style="text-align: center; margin-top: 4rem;">No jobs printed yet.</div>';
                } else {
                    historyList.innerHTML = data.history.map(job => {
                        const badgeClass = job.status === 'COMPLETED' ? 'badge-success' : (job.status === 'FAILED' ? 'badge-failed' : 'badge-pending');
                        return `
                            <div class="history-item">
                                <div class="item-info">
                                    <span class="item-id">${job.job_id}</span>
                                    <span class="item-time">${job.timestamp}</span>
                                </div>
                                <span class="badge ${badgeClass}">${job.status}</span>
                            </div>
                        `;
                    }).join('');
                }

                // Restore active status styling if previously disconnected
                document.getElementById('status-text').textContent = 'Polling Active';
                document.getElementById('global-status').style.borderColor = 'rgba(16, 185, 129, 0.3)';
                document.getElementById('global-status').style.color = 'var(--success)';
                document.getElementById('global-status').style.background = 'var(--success-glow)';

            } catch (err) {
                console.error("Failed to fetch status: ", err);
                document.getElementById('status-text').textContent = 'Connection Lost';
                document.getElementById('global-status').style.borderColor = 'rgba(239, 68, 68, 0.3)';
                document.getElementById('global-status').style.color = 'var(--danger)';
                document.getElementById('global-status').style.background = 'var(--danger-glow)';
            }
        }

        async function fetchLogs() {
            try {
                const response = await fetch('/api/logs');
                const logs = await response.json();
                
                const consoleLogs = document.getElementById('console-logs');
                const wasAtBottom = consoleLogs.scrollHeight - consoleLogs.clientHeight <= consoleLogs.scrollTop + 30;
                
                consoleLogs.innerHTML = logs.map(line => {
                    let color = '#9ca3af'; // default gray for normal lines
                    if (line.includes('[INFO]')) color = '#34d399'; // emerald green for info
                    if (line.includes('[WARNING]')) color = '#fbbf24'; // amber for warning
                    if (line.includes('[ERROR]')) color = '#f87171'; // cherry red for error
                    return `<div style="color: ${color}; line-height: 1.4; margin-bottom: 0.15rem;">${line}</div>`;
                }).join('');
                
                if (wasAtBottom || consoleLogs.scrollTop === 0) {
                    consoleLogs.scrollTop = consoleLogs.scrollHeight;
                }
            } catch (err) {
                console.error("Failed to fetch logs: ", err);
            }
        }

        async function triggerTestPrint() {
            try {
                const response = await fetch('/api/test-print', { method: 'POST' });
                const result = await response.json();
                if (result.success) {
                    alert('Test print job triggered successfully!');
                    fetchStatus();
                } else {
                    alert('Failed to trigger test print: ' + result.error);
                }
            } catch (err) {
                alert('Request failed: ' + err);
            }
        }

        // Poll endpoints
        fetchStatus();
        fetchLogs();
        setInterval(fetchStatus, 2000);
        setInterval(fetchLogs, 1000);
    </script>
</body>
</html>
"""

# Base HTTP request handler for dashboard API endpoints
class DashboardHTTPRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence HTTP connection logs from flooding console
        pass

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(INDEX_HTML.encode("utf-8"))

        elif self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            status_data = {
                "station_id": DashboardState.station_id,
                "api_base_url": DashboardState.api_base_url,
                "poll_interval": DashboardState.poll_interval,
                "history": DashboardState.history
            }
            self.wfile.write(json.dumps(status_data).encode("utf-8"))

        elif self.path == "/api/logs":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(list(DashboardState.logs_queue)).encode("utf-8"))

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/api/test-print":
            import tempfile
            from app.printer_service import PrinterService
            from app.config import Config

            # Generate a test PDF locally and feed it into printer service
            fd, temp_path = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)
            try:
                with open(temp_path, "wb") as f:
                    f.write(TEST_PDF_BYTES)

                # Attempt print
                logger.info("Triggered Diagnostic Test Print")
                success = PrinterService.print_pdf_to_default(temp_path, Config.SELECTED_PRINTER)
                
                if success:
                    DashboardState.add_job("DIAGNOSTIC_TEST", "COMPLETED")
                    response = {"success": True}
                else:
                    DashboardState.add_job("DIAGNOSTIC_TEST", "FAILED", "Print failed")
                    response = {"success": False, "error": "PrinterService rejected print job."}
            except Exception as e:
                logger.error(f"Test print exception: {e}")
                DashboardState.add_job("DIAGNOSTIC_TEST", "FAILED", str(e))
                response = {"success": False, "error": str(e)}
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

# Server launcher run in background thread
def start_dashboard_server(port=5001):
    def run():
        server_address = ('127.0.0.1', port)
        httpd = HTTPServer(server_address, DashboardHTTPRequestHandler)
        logger.info(f"Dashboard Console UI available at: http://localhost:{port}")
        httpd.serve_forever()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
