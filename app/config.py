import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    API_BASE_URL = os.getenv(
        "API_BASE_URL",
        "http://127.0.0.1:8000/api/v1/print"
    )

    POLL_INTERVAL = int(
        os.getenv("POLL_INTERVAL", "5")
    )

    STATION_ID = os.getenv(
        "STATION_ID",
        "PACK_STATION_01"
    )

    SELECTED_PRINTER = os.getenv(
        "SELECTED_PRINTER",
        "Default System Printer"
    )