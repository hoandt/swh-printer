import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    API_BASE_URL = os.getenv(
        "API_BASE_URL",
        "https://print.swifthub.net/api/v1/print"
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