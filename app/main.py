from app.gateway import PrintGateway
from app.gui import run_gui_app

def main():

    gateway = PrintGateway()
    run_gui_app(gateway)