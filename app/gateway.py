import os
import time
import tempfile
import requests

from app.config import Config
from app.logger import logger
from app.printer_service import PrinterService
from app.dashboard import start_dashboard_server, DashboardState


class PrintGateway:

    def __init__(self):

        self.session = requests.Session()

        self.session.headers.update({
            "X-Station-ID": Config.STATION_ID
        })

        self.processed_jobs = set()

        # Initialize dashboard settings and start dashboard UI in a background thread
        DashboardState.station_id = Config.STATION_ID
        DashboardState.api_base_url = Config.API_BASE_URL
        DashboardState.poll_interval = Config.POLL_INTERVAL
        start_dashboard_server(port=5001)

    # ========================================
    # FETCH QUEUE
    # ========================================

    def fetch_jobs(self):

        try:

            response = self.session.get(
                f"{Config.API_BASE_URL}/queue",
                timeout=10
            )

            if response.status_code != 200:
                return []

            payload = response.json()

            if not payload.get("success"):
                return []

            return payload.get("data", [])

        except Exception as e:
            logger.warning(f"Fetch failed: {e}")
            return []

    # ========================================
    # ACKNOWLEDGE
    # ========================================

    def acknowledge_job(
        self,
        job_id: str,
        status: str,
        error: str = None
    ):

        payload = {
            "job_id": job_id,
            "status": status,
            "error_message": error
        }

        try:

            self.session.post(
                f"{Config.API_BASE_URL}/ack",
                json=payload,
                timeout=10
            )

            logger.info(
                f"ACK {job_id} -> {status}"
            )

        except Exception as e:
            logger.error(
                f"ACK failed for {job_id}: {e}"
            )

    # ========================================
    # PROCESS JOB
    # ========================================

    def process_job(self, job: dict):

        job_id = job.get("job_id")
        file_url = job.get("file_url")

        if not job_id or not file_url:
            return

        # Prevent duplicate printing
        if job_id in self.processed_jobs:
            return

        self.processed_jobs.add(job_id)

        logger.info(f"Processing {job_id}")

        fd, temp_path = tempfile.mkstemp(
            suffix=".pdf"
        )

        os.close(fd)

        try:

            # ============================
            # DOWNLOAD PDF
            # ============================

            with self.session.get(
                file_url,
                stream=True,
                timeout=30
            ) as response:

                response.raise_for_status()

                with open(temp_path, "wb") as f:

                    for chunk in response.iter_content(
                        chunk_size=8192
                    ):
                        f.write(chunk)

            # ============================
            # PRINT
            # ============================

            success = PrinterService.print_pdf_to_default(
                temp_path,
                Config.SELECTED_PRINTER
            )

            if success:

                self.acknowledge_job(
                    job_id,
                    "COMPLETED"
                )
                DashboardState.add_job(job_id, "COMPLETED")

            else:

                self.acknowledge_job(
                    job_id,
                    "FAILED",
                    "Print failed"
                )
                DashboardState.add_job(job_id, "FAILED", "Print failed")

        except Exception as e:

            logger.error(
                f"Job failed {job_id}: {e}"
            )

            self.acknowledge_job(
                job_id,
                "FAILED",
                str(e)
            )
            DashboardState.add_job(job_id, "FAILED", str(e))

        finally:

            if os.path.exists(temp_path):
                os.remove(temp_path)

    # ========================================
    # MAIN LOOP
    # ========================================

    def run(self):

        logger.info(
            f"Station: {Config.STATION_ID}"
        )

        logger.info(
            f"Polling: {Config.API_BASE_URL}"
        )

        while True:

            try:

                jobs = self.fetch_jobs()

                for job in jobs:
                    self.process_job(job)

            except Exception as e:
                logger.error(
                    f"Main loop error: {e}"
                )

            time.sleep(Config.POLL_INTERVAL)