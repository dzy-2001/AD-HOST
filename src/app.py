"""Qt application composition root."""
import os
os.environ['QT_API']='pyqt6'
from PyQt6.QtWidgets import QApplication
from .views.widgets.theme import apply_theme
from .views.main_window import MainWindow
from .controllers.acquisition_controller import AcquisitionController


def create_application(argv=None):
    app=QApplication.instance() or QApplication(argv or [])
    app.setApplicationName('AD-HOST');app.setOrganizationName('AD-HOST');apply_theme(app)
    window=MainWindow();controller=AcquisitionController(window);window.controller=controller
    return app,window,controller


def main():
    import sys
    app,window,controller=create_application(sys.argv);window.show();return app.exec()
