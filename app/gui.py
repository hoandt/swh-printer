import os
import queue
import logging
import threading
import webbrowser
from datetime import datetime

# Graceful import check for Tkinter support
try:
    import tkinter as tk
    from tkinter import ttk, messagebox
    HAS_TKINTER = True
except ImportError:
    HAS_TKINTER = False

from app.config import Config
from app.logger import logger
from app.printer_service import PrinterService
from app.dashboard import start_dashboard_server, DashboardState

# Queue to transport logs thread-safely from the background to the UI
log_queue = queue.Queue()

class GUIQueueHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] - %(message)s"))

    def emit(self, record):
        try:
            msg = self.format(record)
            log_queue.put(msg)
        except Exception:
            pass

import platform
import subprocess

# Register the GUI logger queue handler
gui_log_handler = GUIQueueHandler()
logging.getLogger("SimplePrintGateway").addHandler(gui_log_handler)


def get_available_printers():
    printers = ["Default System Printer"]
    current_os = platform.system().lower()
    try:
        if "darwin" in current_os or "linux" in current_os:
            result = subprocess.run(["lpstat", "-p"], capture_output=True, text=True, timeout=5)
            for line in result.stdout.splitlines():
                if line.startswith("printer "):
                    parts = line.split()
                    if len(parts) > 1:
                        printers.append(parts[1])
        elif "windows" in current_os:
            result = subprocess.run(
                ["powershell", "-Command", "Get-Printer | Select-Object -ExpandProperty Name"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                name = line.strip()
                if name:
                    printers.append(name)
    except Exception as e:
        logger.warning(f"Error fetching printers: {e}")
    return printers


class ModernButton(tk.Label):
    def __init__(self, parent, text, command, bg_color, fg_color, hover_color, font, pady=6, padx=15, **kwargs):
        super().__init__(
            parent, 
            text=text, 
            bg=bg_color, 
            fg=fg_color, 
            font=font, 
            pady=pady, 
            padx=padx, 
            relief="flat", 
            bd=0, 
            cursor="hand2",
            **kwargs
        )
        self.command = command
        self.bg_color = bg_color
        self.hover_color = hover_color
        
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        
    def _on_click(self, event):
        if self.cget("state") != "disabled":
            self.command()
            
    def _on_enter(self, event):
        if self.cget("state") != "disabled":
            self.configure(bg=self.hover_color)
            
    def _on_leave(self, event):
        if self.cget("state") != "disabled":
            self.configure(bg=self.bg_color)

    def configure(self, **kwargs):
        if "state" in kwargs:
            state = kwargs["state"]
            if state == "disabled":
                super().configure(state="disabled", fg="#6b7280", bg="#1f2937")
                return
            else:
                super().configure(state="normal", fg="white", bg=self.bg_color)
            del kwargs["state"]
        if "bg" in kwargs:
            self.bg_color = kwargs["bg"]
            # Dynamically select appropriate hover color
            if self.bg_color == "#ef4444" or self.bg_color == "red":  # danger
                self.hover_color = "#dc2626"
            elif self.bg_color == "#10b981" or self.bg_color == "green":  # success
                self.hover_color = "#059669"
            elif self.bg_color == "#3b82f6" or self.bg_color == "blue":  # primary
                self.hover_color = "#2563eb"
            elif self.bg_color == "#4b5563":  # gray
                self.hover_color = "#374151"
        if "hover_color" in kwargs:
            self.hover_color = kwargs["hover_color"]
        super().configure(**kwargs)
        
    def config(self, **kwargs):
        self.configure(**kwargs)


class ModernPrintGatewayGUI:
    def __init__(self, root, gateway):
        self.root = root
        self.gateway = gateway
        self.is_polling = False
        self.polling_thread = None
        self.stop_event = threading.Event()

        # Window configuration
        self.root.title("Print Gateway Control Center")
        self.root.geometry("750x580")
        self.root.minsize(700, 520)
        self.root.configure(bg="#0b0f19")

        # Color system
        self.colors = {
            "bg": "#0b0f19",
            "card": "#111827",
            "card_border": "#1f2937",
            "primary": "#3b82f6",
            "primary_hover": "#2563eb",
            "text": "#f3f4f6",
            "text_muted": "#9ca3af",
            "success": "#10b981",
            "danger": "#ef4444",
            "warning": "#f59e0b",
            "console_bg": "#030712"
        }

        # Apply custom theme styling to ttk
        self.style = ttk.Style()
        self.style.theme_use("clam")
        
        # Configure frames and elements
        self.style.configure("TFrame", background=self.colors["bg"])
        self.style.configure("Card.TFrame", background=self.colors["card"], borderwidth=1, relief="solid")
        
        self.create_widgets()
        self.start_polling_action() # Auto-start polling on UI launch

        # Set up periodic polling of log queue
        self.root.after(100, self.poll_logs)
        self.root.after(1000, self.update_statistics)

    def create_widgets(self):
        # 1. HEADER SECTION
        header_frame = tk.Frame(self.root, bg=self.colors["bg"], pady=15, padx=20)
        header_frame.pack(fill="x", padx=20)

        # Title
        title_frame = tk.Frame(header_frame, bg=self.colors["bg"])
        title_frame.pack(side="left")
        
        title_lbl = tk.Label(
            title_frame, 
            text="Print Gateway Console", 
            font=(".AppleSystemUIFont", 18, "bold") if os.name != "nt" else ("Segoe UI", 18, "bold"), 
            fg=self.colors["text"], 
            bg=self.colors["bg"]
        )
        title_lbl.pack(anchor="w")

        sub_lbl = tk.Label(
            title_frame,
            text=f"Station Station ID: {Config.STATION_ID}",
            font=(".AppleSystemUIFont", 11) if os.name != "nt" else ("Segoe UI", 11),
            fg=self.colors["text_muted"],
            bg=self.colors["bg"]
        )
        sub_lbl.pack(anchor="w", pady=2)

        # Status badge canvas (circle)
        self.status_canvas = tk.Canvas(header_frame, width=130, height=35, bg=self.colors["bg"], highlightthickness=0)
        self.status_canvas.pack(side="right")
        self.draw_status_indicator("IDLE", self.colors["warning"])

        # 2. STATS & CONTROLS SECTION
        main_content = tk.Frame(self.root, bg=self.colors["bg"])
        main_content.pack(fill="both", expand=True, padx=20)

        # Grid system for settings and actions
        top_grid = tk.Frame(main_content, bg=self.colors["bg"])
        top_grid.pack(fill="x", pady=10)

        # --- Left Side: Configuration Card ---
        config_card = tk.LabelFrame(
            top_grid, 
            text=" CONFIGURATION ", 
            font=(".AppleSystemUIFont", 9, "bold") if os.name != "nt" else ("Segoe UI", 9, "bold"),
            fg=self.colors["primary"],
            bg=self.colors["card"],
            bd=1,
            relief="solid",
            padx=15,
            pady=10
        )
        config_card.pack(side="left", fill="both", expand=True, padx=(0, 10))
        config_card.configure(fg=self.colors["primary"])

        # Config fields
        endpoint_lbl = tk.Label(config_card, text="Endpoint:", font=("Helvetica", 10, "bold"), fg=self.colors["text_muted"], bg=self.colors["card"])
        endpoint_lbl.grid(row=0, column=0, sticky="w", pady=3)
        self.endpoint_val = tk.Label(config_card, text=Config.API_BASE_URL, font=("Courier", 10), fg=self.colors["text"], bg=self.colors["card"])
        self.endpoint_val.grid(row=0, column=1, sticky="w", padx=10, pady=3)

        interval_lbl = tk.Label(config_card, text="Interval:", font=("Helvetica", 10, "bold"), fg=self.colors["text_muted"], bg=self.colors["card"])
        interval_lbl.grid(row=1, column=0, sticky="w", pady=3)
        self.interval_val = tk.Label(config_card, text=f"{Config.POLL_INTERVAL} seconds", font=("Helvetica", 10), fg=self.colors["text"], bg=self.colors["card"])
        self.interval_val.grid(row=1, column=1, sticky="w", padx=10, pady=3)

        stats_lbl = tk.Label(config_card, text="Processed:", font=("Helvetica", 10, "bold"), fg=self.colors["text_muted"], bg=self.colors["card"])
        stats_lbl.grid(row=2, column=0, sticky="w", pady=3)
        self.stats_val = tk.Label(config_card, text="0 Succeeded / 0 Failed", font=("Helvetica", 10), fg=self.colors["text"], bg=self.colors["card"])
        self.stats_val.grid(row=2, column=1, sticky="w", padx=10, pady=3)

        # Printer selection dropdown
        printer_lbl = tk.Label(config_card, text="Printer:", font=("Helvetica", 10, "bold"), fg=self.colors["text_muted"], bg=self.colors["card"])
        printer_lbl.grid(row=3, column=0, sticky="nw", pady=6)

        printer_frame = tk.Frame(config_card, bg=self.colors["card"])
        printer_frame.grid(row=3, column=1, sticky="w", padx=10, pady=3)

        self.printer_var = tk.StringVar(value=Config.SELECTED_PRINTER)
        self.printer_dropdown = ttk.Combobox(
            printer_frame,
            textvariable=self.printer_var,
            values=get_available_printers(),
            state="readonly",
            width=18
        )
        self.printer_dropdown.pack(side="left", padx=(0, 5))

        def on_printer_select(event):
            Config.SELECTED_PRINTER = self.printer_var.get()
            logger.info(f"Selected printer updated to: {Config.SELECTED_PRINTER}")

        self.printer_dropdown.bind("<<ComboboxSelected>>", on_printer_select)

        self.lock_var = tk.BooleanVar(value=False)
        self.lock_checkbox = tk.Checkbutton(
            printer_frame,
            text="Lock",
            variable=self.lock_var,
            onvalue=True,
            offvalue=False,
            bg=self.colors["card"],
            fg=self.colors["text_muted"],
            selectcolor=self.colors["bg"],
            activebackground=self.colors["card"],
            activeforeground=self.colors["text"],
            font=("Helvetica", 9, "bold"),
            command=self.toggle_printer_lock,
            bd=0,
            highlightthickness=0
        )
        self.lock_checkbox.pack(side="left")

        # --- Right Side: Actions Card ---
        actions_card = tk.LabelFrame(
            top_grid,
            text=" CONTROL ACTIONS ",
            font=(".AppleSystemUIFont", 9, "bold") if os.name != "nt" else ("Segoe UI", 9, "bold"),
            fg=self.colors["primary"],
            bg=self.colors["card"],
            bd=1,
            relief="solid",
            padx=15,
            pady=10
        )
        actions_card.pack(side="right", fill="both", expand=True)

        self.btn_poll = ModernButton(
            actions_card, 
            text="Stop Polling Gateway", 
            command=self.toggle_polling, 
            bg_color=self.colors["danger"], 
            fg_color="white", 
            hover_color="#dc2626",
            font=("Helvetica", 10, "bold"), 
            pady=6,
            padx=15
        )
        self.btn_poll.pack(fill="x", pady=4)

        self.btn_test = ModernButton(
            actions_card,
            text="Print Test Ticket ⚡",
            command=self.print_test_page,
            bg_color=self.colors["primary"],
            fg_color="white",
            hover_color="#2563eb",
            font=("Helvetica", 10, "bold"),
            pady=6,
            padx=15
        )
        self.btn_test.pack(fill="x", pady=4)

        self.btn_dash = ModernButton(
            actions_card,
            text="Open Web Dashboard 🖥️",
            command=lambda: webbrowser.open("http://localhost:5001"),
            bg_color="#4b5563",
            fg_color="white",
            hover_color="#374151",
            font=("Helvetica", 10, "bold"),
            pady=6,
            padx=15
        )
        self.btn_dash.pack(fill="x", pady=4)

        # 3. CONSOLE LOGS SECTION
        console_lbl = tk.Label(
            main_content, 
            text="📟 SYSTEM LOGSTREAM", 
            font=(".AppleSystemUIFont", 10, "bold") if os.name != "nt" else ("Segoe UI", 10, "bold"), 
            fg=self.colors["text_muted"], 
            bg=self.colors["bg"]
        )
        console_lbl.pack(anchor="w", pady=(15, 5))

        console_frame = tk.Frame(main_content, bg=self.colors["console_bg"])
        console_frame.pack(fill="both", expand=True, pady=(0, 15))

        self.console_txt = tk.Text(
            console_frame,
            bg=self.colors["console_bg"],
            fg="#10b981",  # Terminal green
            font=("Courier", 10) if os.name != "nt" else ("Consolas", 10),
            wrap="word",
            bd=0,
            padx=10,
            pady=10,
            insertbackground="white"
        )
        self.console_txt.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(console_frame, bg=self.colors["console_bg"])
        scrollbar.pack(side="right", fill="y")

        self.console_txt.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.console_txt.yview)

    def draw_status_indicator(self, text, color):
        self.status_canvas.delete("all")
        # Draw status container border/background
        self.status_canvas.create_rounded_rect(3, 3, 127, 32, r=14, fill=self.colors["card"], outline=color, width=1.5)
        # Pulsing circle indicator
        self.status_canvas.create_oval(15, 12, 23, 20, fill=color, outline="")
        # Status text
        self.status_canvas.create_text(68, 17, text=text, fill=color, font=("Helvetica", 10, "bold"))

    def toggle_printer_lock(self):
        if self.lock_var.get():
            self.printer_dropdown.config(state="disabled")
            logger.info(f"Printer selection LOCKED: {Config.SELECTED_PRINTER}")
        else:
            self.printer_dropdown.config(state="readonly")
            logger.info("Printer selection UNLOCKED")

    def toggle_polling(self):
        if self.is_polling:
            self.stop_polling_action()
        else:
            self.start_polling_action()

    def start_polling_action(self):
        self.is_polling = True
        self.btn_poll.config(text="Stop Polling Gateway", bg=self.colors["danger"])
        self.draw_status_indicator("POLLING", self.colors["success"])
        
        self.stop_event.clear()
        # Start gateway loop in a separate thread
        self.polling_thread = threading.Thread(target=self.run_gateway_loop, daemon=True)
        self.polling_thread.start()
        logger.info("Gateway Polling Engine successfully started.")

    def stop_polling_action(self):
        self.is_polling = False
        self.btn_poll.config(text="Start Polling Gateway", bg=self.colors["success"])
        self.draw_status_indicator("PAUSED", self.colors["warning"])
        self.stop_event.set()
        logger.warning("Gateway Polling Engine paused by user.")

    def print_test_page(self):
        self.btn_test.config(state="disabled")
        logger.info("Triggered diagnostic test print via Native Control Panel")
        
        # Run printing in a brief helper thread to avoid UI freeze
        def print_task():
            import tempfile
            from app.dashboard import TEST_PDF_BYTES
            
            fd, temp_path = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)
            try:
                with open(temp_path, "wb") as f:
                    f.write(TEST_PDF_BYTES)
                
                success = PrinterService.print_pdf_to_default(temp_path, Config.SELECTED_PRINTER)
                if success:
                    DashboardState.add_job("GUI_DIAGNOSTIC_TEST", "COMPLETED")
                    logger.info("Diagnostic Test Print COMPLETED successfully.")
                else:
                    DashboardState.add_job("GUI_DIAGNOSTIC_TEST", "FAILED", "Print failed")
                    logger.error("Diagnostic Test Print FAILED.")
            except Exception as e:
                logger.error(f"Diagnostic print error: {e}")
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                self.root.after(0, lambda: self.btn_test.config(state="normal"))

        threading.Thread(target=print_task, daemon=True).start()

    def run_gateway_loop(self):
        # Custom run loop responding to the UI's stop event
        logger.info(f"Station ID: {Config.STATION_ID} is listening...")
        while not self.stop_event.is_set():
            try:
                jobs = self.gateway.fetch_jobs()
                for job in jobs:
                    if self.stop_event.is_set():
                        break
                    self.gateway.process_job(job)
            except Exception as e:
                logger.error(f"Polling loop error: {e}")
            
            # Sleep in tiny increments to remain highly responsive to the Stop event
            for _ in range(Config.POLL_INTERVAL * 10):
                if self.stop_event.is_set():
                    break
                threading.Event().wait(0.1)

    def poll_logs(self):
        # Poll logs thread-safely from the logging queue
        while True:
            try:
                msg = log_queue.get_nowait()
                self.console_txt.insert(tk.END, msg + "\n")
                self.console_txt.see(tk.END)
                log_queue.task_done()
            except queue.Empty:
                break
        
        self.root.after(100, self.poll_logs)

    def update_statistics(self):
        # Fetch status variables and display them on the card
        total = len(DashboardState.history)
        succeeded = len([j for j in DashboardState.history if j["status"] == "COMPLETED"])
        failed = total - succeeded
        self.stats_val.config(text=f"{succeeded} Succeeded / {failed} Failed")
        self.root.after(1000, self.update_statistics)


# Helper helper to draw smooth rounded rectangles in Tkinter canvas
def _create_rounded_rect(self, x1, y1, x2, y2, r=25, **kwargs):
    points = [
        x1+r, y1, x1+r, y1, x2-r, y1, x2-r, y1,
        x2, y1, x2, y1+r, x2, y1+r, x2, y2-r,
        x2, y2-r, x2, y2, x2-r, y2, x2-r, y2,
        x1+r, y2, x1+r, y2, x1, y2, x1, y2-r,
        x1, y2-r, x1, y1+r, x1, y1+r, x1, y1
    ]
    return self.create_polygon(points, **kwargs, smooth=True)

tk.Canvas.create_rounded_rect = _create_rounded_rect


def run_gui_app(gateway):
    if not HAS_TKINTER:
        print("[WARNING] Tkinter / TclTk not found on this system.")
        print("[FALLBACK] Launching print-gateway in standard terminal CLI mode...")
        gateway.run()
        return

    root = tk.Tk()
    
    # Configure nice style parameters for windows vs mac
    try:
        # Standardize macOS full-color look
        if os.name != "nt":
            root.tk.call('tk', 'windowingsystem')
    except Exception:
        pass

    app = ModernPrintGatewayGUI(root, gateway)
    
    def on_closing():
        app.stop_polling_action()
        root.destroy()
        
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()
