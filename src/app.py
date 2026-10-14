"""Qt application composition root; show startup art before heavy UI imports."""
import os
os.environ['QT_API']='pyqt6'
from PyQt6.QtWidgets import QApplication
from .resources import set_windows_app_id
from .views.widgets.branding import application_icon,StartupSplash


def create_application(argv=None,*,show_splash=False):
    if QApplication.instance() is None:set_windows_app_id()
    app=QApplication.instance() or QApplication(argv or [])
    app.setApplicationName('AD-HOST');app.setOrganizationName('AD-HOST');app.setWindowIcon(application_icon())
    splash=StartupSplash(app) if show_splash else None
    try:
        from .views.widgets.theme import apply_theme
        from .views.main_window import MainWindow
        from .controllers.acquisition_controller import AcquisitionController
        apply_theme(app)
        window=MainWindow();controller=AcquisitionController(window)
        window.controller=controller;window.startup_splash=splash
        return app,window,controller
    except BaseException:
        if splash:splash.close()
        raise


def main():
    import sys
    app,window,controller=create_application(sys.argv,show_splash=True)
    window.show();app.processEvents()
    window.startup_splash.finish(window)
    return app.exec()
