import os
import sys
import platform
import subprocess
from pathlib import Path

from app.logger import logger


class PrinterService:

    @staticmethod
    def print_pdf_to_default(file_path: str, printer_name: str = None) -> bool:
        current_os = platform.system().lower()

        try:
            pdf_path = Path(file_path).resolve()
            if not pdf_path.exists():
                raise FileNotFoundError(f"PDF file not found at: {pdf_path}")

            # ====================================
            # WINDOWS
            # ====================================
            if "windows" in current_os:
                
                # Check if running inside a PyInstaller bundle
                if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
                    # PyInstaller temporary extraction path
                    base_path = Path(sys._MEIPASS)
                    bundled_sumatra = base_path / "bin" / "SumatraPDF.exe"
                else:
                    # Normal local development path
                    script_dir = Path(__file__).resolve().parent
                    project_root = script_dir.parent
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
                    raise FileNotFoundError(f"SumatraPDF executable not found. Looked at: {bundled_sumatra}")

                logger.info(f"Using SumatraPDF engine at: {sumatra}")

                if printer_name and printer_name != "Default System Printer":
                    cmd = [sumatra, "-print-to", printer_name, "-silent", str(pdf_path)]
                else:
                    cmd = [sumatra, "-print-to-default", "-silent", str(pdf_path)]

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

                subprocess.run(cmd, check=True, timeout=30, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            else:
                raise Exception(f"Unsupported OS: {current_os}")

            logger.info(f"Print success on printer: {printer_name or 'Default'}")
            return True

        except Exception as e:
            logger.error(f"Printing failed: {e}")
            return False