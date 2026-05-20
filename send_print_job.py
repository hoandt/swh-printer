import requests
import json

# ==============================================================================
# SAMPLE PRINT SUBMISSION SCRIPT
# ==============================================================================
# This script sends a POST request to enqueue print jobs on the mock server.
# Once enqueued, the Print Gateway will automatically fetch, download, and print them!
# ==============================================================================

# 1. Server Endpoint
# The mock server runs on port 2401. We enqueued the job using '/api/v1/print/enqueue'
URL = "http://127.0.0.1:2401/api/v1/print/enqueue"

# 2. Sample Payloads
# A. Custom external PDF URL
payload_custom = {
    "file_url": "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf",
    "document_type": "AWB"
}

# B. Default Server Mock PDF (omitting 'file_url' tells the server to auto-generate a valid mock PDF)
payload_default = {
    "document_type": "PACKING_SLIP"
}

def submit_job(payload):
    print(f"Sending POST request to {URL}...")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(
            URL, 
            json=payload, 
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        if response.status_code == 201:
            data = response.json()
            print("✅ SUCCESS!")
            print(f"   Job ID: {data.get('job_id')}")
            print(f"   Message: {data.get('message')}\n")
        else:
            print(f"❌ FAILED (Status Code {response.status_code}): {response.text}\n")
            
    except requests.exceptions.ConnectionError:
        print("❌ CONNECTION ERROR: Is your mock_server.py running on http://127.0.0.1:2401?\n")
    except Exception as e:
        print(f"❌ ERROR: {e}\n")


if __name__ == "__main__":
    print("==============================================")
    print("🚀 SUBMITTING PRINT JOBS TO THE LOCAL SERVER")
    print("==============================================\n")
    
    # 1. Submit a custom internet PDF
    submit_job(payload_custom)
    
    # 2. Submit using the server's default mock PDF generator
    submit_job(payload_default)

# ==============================================================================
# ALTERNATIVE: HOW TO DO THIS VIA CURL IN THE TERMINAL
# ==============================================================================
# You can run either of these commands directly from your terminal:
#
# 1. To print a custom PDF:
#    curl -X POST http://127.0.0.1:2401/api/v1/print/enqueue \
#         -H "Content-Type: application/json" \
#         -d '{"file_url": "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf", "document_type": "AWB"}'
#
# 2. To print a default mock PDF:
#    curl -X POST http://127.0.0.1:2401/api/v1/print/enqueue \
#         -H "Content-Type: application/json" \
#         -d '{"document_type": "PACKING_SLIP"}'
# ==============================================================================
