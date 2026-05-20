import os
import json
import uuid
import sqlite3
import logging
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# Configure structured production logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] - %(message)s"
)
logger = logging.getLogger("MockPrintServer")

# ==============================================================================
# CONFIGURATION
# ==============================================================================
DB_PATH = os.environ.get("DATABASE_PATH", "jobs.db")
# Set PRODUCTION=true in environment to disable auto-generating dev mock jobs
IS_PRODUCTION = os.environ.get("PRODUCTION", "false").lower() in ("true", "1", "yes")
# Lease/Visibility timeout in seconds (if a station claims a job but doesn't ACK within this time, it becomes re-claimable)
CLAIM_TIMEOUT_SECONDS = int(os.environ.get("CLAIM_TIMEOUT_SECONDS", "300"))

# A valid minimal PDF that renders "Mock Print Job" text
MINIMAL_PDF = (
    b'%PDF-1.4\n'
    b'1 0 obj <</Type/Catalog/Pages 2 0 R>> endobj\n'
    b'2 0 obj <</Type/Pages/Kids[3 0 R]/Count 1>> endobj\n'
    b'3 0 obj <</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>> endobj\n'
    b'4 0 obj <</Type/Font/Subtype/Type1/BaseFont/Helvetica>> endobj\n'
    b'5 0 obj <</Length 44>> stream\n'
    b'BT\n/F1 24 Tf\n100 700 Td\n(Mock Print Job) Tj\nET\n'
    b'endstream\n'
    b'endobj\n'
    b'xref\n'
    b'0 6\n'
    b'0000000000 65535 f \n'
    b'0000000009 00000 n \n'
    b'0000000056 00000 n \n'
    b'0000000111 00000 n \n'
    b'0000000223 00000 n \n'
    b'0000000290 00000 n \n'
    b'trailer <</Size 6/Root 1 0 R>>\n'
    b'startxref\n'
    b'385\n'
    b'%%EOF\n'
)

# ==============================================================================
# DATABASE SETUP
# ==============================================================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            file_url TEXT NOT NULL,
            document_type TEXT NOT NULL,
            status TEXT NOT NULL,
            error_message TEXT,
            claimed_by TEXT,
            claimed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Run migrations dynamically to support upgrading from older databases smoothly
    try:
        cursor.execute("ALTER TABLE jobs ADD COLUMN claimed_by TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists
        
    try:
        cursor.execute("ALTER TABLE jobs ADD COLUMN claimed_at TIMESTAMP")
    except sqlite3.OperationalError:
        pass  # Column already exists

    conn.commit()
    conn.close()
    logger.info(f"Database initialized at {DB_PATH}")

# ==============================================================================
# HTTP HANDLER
# ==============================================================================
class MockPrintServerHandler(BaseHTTPRequestHandler):
    
    def log_message(self, format, *args):
        # Prevent BaseHTTPRequestHandler from writing raw logs to stdout
        pass

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Station-ID")

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/v1/print/queue":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._send_cors_headers()
            self.end_headers()
            
            # Read Station ID from standard header
            station_id = self.headers.get("X-Station-ID", "UNKNOWN_STATION")
            
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # 1. Fetch any jobs already CLAIMED by this station (for retry/resume safety)
            cursor.execute(
                "SELECT job_id, file_url, document_type FROM jobs WHERE status = 'CLAIMED' AND claimed_by = ?",
                (station_id,)
            )
            rows = cursor.fetchall()
            
            # 2. If the station has no active claimed jobs, atomically claim new ones!
            if not rows:
                try:
                    # BEGIN IMMEDIATE locks the SQLite database during the transaction, preventing race conditions
                    conn.execute("BEGIN IMMEDIATE")
                    
                    # Select jobs that are either PENDING, or CLAIMED but exceeded visibility lease timeout
                    cursor.execute(
                        """
                        SELECT job_id FROM jobs 
                        WHERE status = 'PENDING' 
                           OR (status = 'CLAIMED' AND strftime('%s', 'now') - strftime('%s', claimed_at) > ?)
                        ORDER BY created_at ASC LIMIT 5
                        """,
                        (CLAIM_TIMEOUT_SECONDS,)
                    )
                    pending_ids = [r[0] for r in cursor.fetchall()]
                    
                    if pending_ids:
                        placeholders = ",".join("?" for _ in pending_ids)
                        # Atomically claim these jobs for this station
                        cursor.execute(
                            f"""
                            UPDATE jobs 
                            SET status = 'CLAIMED', claimed_by = ?, claimed_at = datetime('now') 
                            WHERE job_id IN ({placeholders})
                            """,
                            [station_id] + pending_ids
                        )
                        conn.commit()
                        logger.info(f"Station '{station_id}' atomically claimed {len(pending_ids)} job(s): {pending_ids}")
                    else:
                        conn.commit()
                        
                        # In development mode, auto-generate a new job if the queue is completely empty
                        if not IS_PRODUCTION:
                            cursor.execute("SELECT COUNT(*) FROM jobs")
                            total_jobs = cursor.fetchone()[0]
                            if total_jobs < 3:
                                new_id = f"job_{uuid.uuid4().hex[:8]}"
                                host = self.headers.get("Host", "localhost:8000")
                                file_url = f"http://{host}/mock_pdf/{new_id}.pdf"
                                
                                conn.execute("BEGIN IMMEDIATE")
                                cursor.execute(
                                    """
                                    INSERT INTO jobs (job_id, file_url, document_type, status, claimed_by, claimed_at) 
                                    VALUES (?, ?, ?, 'CLAIMED', ?, datetime('now'))
                                    """,
                                    (new_id, file_url, "AWB", station_id)
                                )
                                conn.commit()
                                logger.info(f"Dev Mode: Auto-generated & claimed job {new_id} for station {station_id}")
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Error during claim transaction for station '{station_id}': {e}")
                
                # Re-fetch the claimed jobs
                cursor.execute(
                    "SELECT job_id, file_url, document_type FROM jobs WHERE status = 'CLAIMED' AND claimed_by = ?",
                    (station_id,)
                )
                rows = cursor.fetchall()
            
            data = []
            for row in rows:
                data.append({
                    "job_id": row[0],
                    "file_url": row[1],
                    "document_type": row[2]
                })
                
            conn.close()
            
            response = {
                "success": True,
                "data": data
            }
            self.wfile.write(json.dumps(response).encode("utf-8"))
            
        elif self.path.startswith("/mock_pdf/") and self.path.endswith(".pdf"):
            job_id = self.path.split('/')[-1].replace(".pdf", "")
            logger.info(f"Serving PDF binary for job {job_id}")
            
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(len(MINIMAL_PDF)))
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(MINIMAL_PDF)
            
        else:
            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        # 1. POST /api/v1/print/ack
        if self.path == "/api/v1/print/ack":
            try:
                payload = json.loads(post_data.decode('utf-8'))
                job_id = payload.get("job_id")
                status = payload.get("status")
                error_message = payload.get("error_message")
                
                if not job_id or not status:
                    raise ValueError("Missing job_id or status")
                
                logger.info(f"ACK received: Job {job_id} -> {status}" + (f" (Error: {error_message})" if error_message else ""))
                
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE jobs SET status = ?, error_message = ? WHERE job_id = ?",
                    (status, error_message, job_id)
                )
                conn.commit()
                conn.close()
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
                
            except Exception as e:
                logger.error(f"ACK processing error: {e}")
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
                
        # 2. POST /api/v1/print/enqueue
        elif self.path == "/api/v1/print/enqueue":
            try:
                payload = json.loads(post_data.decode('utf-8'))
                job_id = f"job_{uuid.uuid4().hex[:8]}"
                
                host = self.headers.get("Host", "localhost:8000")
                file_url = payload.get("file_url")
                
                # If no URL is provided, default to our internal mock PDF endpoint
                if not file_url:
                    file_url = f"http://{host}/mock_pdf/{job_id}.pdf"
                    
                doc_type = payload.get("document_type", "AWB")
                target_station = payload.get("station_id")
                
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                if target_station:
                    cursor.execute(
                        """
                        INSERT INTO jobs (job_id, file_url, document_type, status, claimed_by, claimed_at) 
                        VALUES (?, ?, ?, 'CLAIMED', ?, datetime('now'))
                        """,
                        (job_id, file_url, doc_type, target_station)
                    )
                else:
                    cursor.execute(
                        "INSERT INTO jobs (job_id, file_url, document_type, status) VALUES (?, ?, ?, 'PENDING')",
                        (job_id, file_url, doc_type)
                    )
                conn.commit()
                conn.close()
                
                logger.info(f"Custom job enqueued: {job_id} -> {file_url}" + (f" (Target Station: {target_station})" if target_station else ""))
                
                self.send_response(201)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({
                    "success": True, 
                    "job_id": job_id, 
                    "message": "Job enqueued successfully"
                }).encode("utf-8"))
                
            except Exception as e:
                logger.error(f"Enqueue error: {e}")
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
                
        else:
            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()

# ==============================================================================
# MAIN RUNNER
# ==============================================================================
def run_server():
    init_db()
    
    # Read host/port from environment variables for production flexibility
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 8000))
    
    server_address = (host, port)
    # ThreadingHTTPServer handles each incoming request concurrently in a thread pool
    httpd = ThreadingHTTPServer(server_address, MockPrintServerHandler)
    
    logger.info(f"==================================================")
    logger.info(f"🚀 Production-Ready Print Server running at http://{host}:{port}")
    logger.info(f"   Mode: {'PRODUCTION (No Autogen)' if IS_PRODUCTION else 'DEVELOPMENT (Auto-generating mock jobs)'}")
    logger.info(f"   Claim Timeout: {CLAIM_TIMEOUT_SECONDS} seconds")
    logger.info(f"==================================================")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping print server...")
        httpd.server_close()

if __name__ == "__main__":
    run_server()
