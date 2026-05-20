import os
import platform
import subprocess

from app.logger import logger


class PrinterService:

    @staticmethod
    def print_pdf_to_default(file_path: str, printer_name: str = None) -> bool:

        current_os = platform.system().lower()

        try:

            # ====================================
            # WINDOWS
            # ====================================
            if "windows" in current_os:

                sumatra_paths = [
                    r"C:\Program Files\SumatraPDF\SumatraPDF.exe",
                    r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe",
                ]

                sumatra = None

                for path in sumatra_paths:
                    if os.path.exists(path):
                        sumatra = path
                        break

                if not sumatra:
                    raise Exception(
                        "SumatraPDF not installed"
                    )

                if printer_name and printer_name != "Default System Printer":
                    cmd = [
                        sumatra,
                        "-print-to",
                        printer_name,
                        "-silent",
                        file_path
                    ]
                else:
                    cmd = [
                        sumatra,
                        "-print-to-default",
                        "-silent",
                        file_path
                    ]

                subprocess.run(
                    cmd,
                    check=True,
                    timeout=30
                )

            # ====================================
            # MACOS + LINUX
            # ====================================
            elif (
                "darwin" in current_os
                or "linux" in current_os
            ):

                cmd = ["lp"]
                if printer_name and printer_name != "Default System Printer":
                    cmd.extend(["-d", printer_name])
                cmd.extend(["-o", "scaling=100", file_path])

                subprocess.run(
                    cmd,
                    check=True,
                    timeout=30,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

            else:
                raise Exception(
                    f"Unsupported OS: {current_os}"
                )

            logger.info(f"Print success on printer: {printer_name or 'Default'}")

            return True

        except subprocess.TimeoutExpired:
            logger.error("Print timeout")
            return False

        except Exception as e:
            logger.error(f"Printing failed: {e}")
            return False