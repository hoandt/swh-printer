import json
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler

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

# In-memory store: job_id -> status
jobs_store = {}
# Custom submitted jobs store: job_id -> job details
custom_jobs = {}

class MockPrintServerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence standard request logging to keep console clean, except for main events
        pass

    def do_GET(self):
        # 1. GET /api/v1/print/queue
        if self.path == "/api/v1/print/queue":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            
            # Find pending jobs
            pending = [jid for jid, status in jobs_store.items() if status == "PENDING"]
            
            # Auto-generate a new job if queue is empty (limit to 3 for safe loop testing)
            if not pending and len(jobs_store) < 3:
                new_id = f"job_{uuid.uuid4().hex[:8]}"
                jobs_store[new_id] = "PENDING"
                pending.append(new_id)
                print(f"[SERVER] Generated new mock job: {new_id}")
            
            data = []
            for jid in pending:
                if jid in custom_jobs:
                    data.append(custom_jobs[jid])
                else:
                    data.append({
                        "job_id": jid,
                        "file_url": f"http://127.0.0.1:8000/mock_pdf/{jid}.pdf",
                        "document_type": "AWB"
                    })
                
            response = {
                "success": True,
                "data": data
            }
            self.wfile.write(json.dumps(response).encode("utf-8"))
            
        # 2. GET /mock_pdf/<job_id>.pdf
        elif self.path.startswith("/mock_pdf/") and self.path.endswith(".pdf"):
            print(f"[SERVER] Serving PDF binary for job {self.path.split('/')[-1]}")
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(len(MINIMAL_PDF)))
            self.end_headers()
            self.wfile.write(MINIMAL_PDF)
            
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        # 3. POST /api/v1/print/ack
        if self.path == "/api/v1/print/ack":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            try:
                payload = json.loads(post_data.decode('utf-8'))
                job_id = payload.get("job_id")
                status = payload.get("status")
                error_message = payload.get("error_message")
                
                print(f"[SERVER ACK] Job {job_id} -> {status}" + (f" (Error: {error_message})" if error_message else ""))
                
                if job_id in jobs_store:
                    jobs_store[job_id] = status
                    
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
                
        # 4. POST /api/v1/print/enqueue (Custom job submission)
        elif self.path == "/api/v1/print/enqueue":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            try:
                payload = json.loads(post_data.decode('utf-8'))
                job_id = f"job_{uuid.uuid4().hex[:8]}"
                
                # Setup custom job details
                file_url = payload.get("file_url", f"http://127.0.0.1:8000/mock_pdf/{job_id}.pdf")
                doc_type = payload.get("document_type", "AWB")
                
                custom_jobs[job_id] = {
                    "job_id": job_id,
                    "file_url": file_url,
                    "document_type": doc_type
                }
                jobs_store[job_id] = "PENDING"
                
                print(f"[SERVER SUBMIT] Received custom job submission {job_id} for URL: {file_url}")
                
                self.send_response(201)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "success": True, 
                    "job_id": job_id, 
                    "message": "Job enqueued successfully"
                }).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
                
        else:
            self.send_response(404)
            self.end_headers()

def run_server(port=8000):
    server_address = ('127.0.0.1', port)
    httpd = HTTPServer(server_address, MockPrintServerHandler)
    print(f"==================================================")
    print(f"🚀 Mock Print Server running at http://127.0.0.1:{port}")
    print(f"==================================================")
    print("This server will auto-generate up to 3 print jobs for testing.")
    print("Press Ctrl+C to exit.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping mock print server.")
        httpd.server_close()

if __name__ == "__main__":
    run_server()
