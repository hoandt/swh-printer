import os
import platform
import subprocess
from pathlib import Path

from app.logger import logger


class PrinterService:

    @staticmethod
    def print_pdf_to_default(file_path: str, printer_name: str = None) -> bool:

        current_os = platform.system().lower()

        try:
            # Resolve target PDF path cleanly
            pdf_path = Path(file_path).resolve()
            if not pdf_path.exists():
                raise FileNotFoundError(f"PDF file not found at: {pdf_path}")

            # ====================================
            # WINDOWS
            # ====================================
            if "windows" in current_os:

                # 1. Check for your bundled executable first
                # Looks inside: project_root/bin/SumatraPDF.exe
                script_dir = Path(__file__).resolve().parent
                project_root = script_dir.parent  # Adjust .parent steps based on where this file lives
                bundled_sumatra = project_root / "bin" / "SumatraPDF.exe"

                sumatra_paths = [
                    bundled_sumatra,
                    r"C:\Program Files\SumatraPDF\SumatraPDF.exe",
                    r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe",
                ]

                sumatra = None
                for path in sumatra_paths:
                    if os.path.exists(path):
                        sumatra = str(path)
                        break

                if not sumatra:
                    raise FileNotFoundError(
                        f"SumatraPDF executable could not be found globally or bundled at: {bundled_sumatra}"
                    )

                logger.info(f"Using SumatraPDF engine at: {sumatra}")

                # 2. Build the command flags
                if printer_name and printer_name != "Default System Printer":
                    cmd = [
                        sumatra,
                        "-print-to",
                        printer_name,
                        "-silent",
                        str(pdf_path)
                    ]
                else:
                    cmd = [
                        sumatra,
                        "-print-to-default",
                        "-silent",
                        str(pdf_path)
                    ]

                # 3. Fire the execution
                subprocess.run(
                    cmd,
                    check=True,
                    timeout=30,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                )

            # ====================================
            # MACOS + LINUX
            # ====================================
            elif "darwin" in current_os or "linux" in current_os:

                cmd = ["lp"]
                if printer_name and printer_name != "Default System Printer":
                    cmd.extend(["-d", printer_name])
                cmd.extend(["-o", "scaling=100", str(pdf_path)])

                subprocess.run(
                    cmd,
                    check=True,
                    timeout=30,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

            else:
                raise Exception(f"Unsupported OS: {current_os}")

            logger.info(f"Print success on printer: {printer_name or 'Default'}")
            return True

        except subprocess.TimeoutExpired:
            logger.error("Print timeout occurred while communicating with the spooler.")
            return False

        except Exception as e:
            logger.error(f"Printing failed: {e}")
            return False