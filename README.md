# Simple Print Gateway

Cross-platform AWB print gateway for warehouse operations.

## Features

- Windows
- macOS
- Linux
- Silent printing
- Poll queue API
- Default printer
- Duplicate protection
- Temporary file cleanup

---

# Install

```bash
pip install -r requirements.txt
```

---

# Configure

Edit `.env`

```env
API_BASE_URL=http://127.0.0.1:8000/api/v1/print
POLL_INTERVAL=5
STATION_ID=PACK_STATION_01
```

---

# Run

```bash
python run.py
```

## Monitor & Control Dashboard

Once the print gateway is running, it starts a local monitoring dashboard in the background. You can open it in your browser:

👉 **[http://localhost:5001](http://localhost:5001)**

Features:
- **Live Status Feed**: Shows connection status and real-time station diagnostics.
- **Productivity Stats**: Tracks job completion counts and success rates.
- **Log Console**: Direct, real-time streaming of all gateway log messages inside the browser window.
- **Diagnostic Controls**: Click `Print Test Page` to immediately print a physical diagnostic test ticket to your default system printer.

---

# macOS/Linux Requirements

Requires CUPS:

```bash
lpstat -p
```

---

# Windows Requirements

Install SumatraPDF:

https://www.sumatrapdfreader.org/download-free-pdf-viewer
