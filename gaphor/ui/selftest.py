import importlib.resources
import logging
import os
import platform
import sys
import textwrap
import time

import cairo
import gi
from gi.repository import Gdk, GLib, Gtk, Pango

from gaphor.abc import Service
from gaphor.application import Application, distribution
from gaphor.core import Transaction
from gaphor.core.modeling import Diagram

log = logging.getLogger(__name__)


class Status:
    def __init__(self, name):
        self.name = name
        self.status = "in progress"

    def complete(self):
        self.status = "completed"

    @property
    def in_progress(self):
        return self.status == "in progress"

    @property
    def completed(self):
        return self.status == "completed"

    def __repr__(self):
        return f"{self.name}: {self.status}"


def test(func):
    """A test function."""

    def wrapper(self):
        status = Status(func.__name__)
        self.statuses.append(status)
        try:
            return func(self, status)
        except BaseException:
            log.exception("Test %s failed", func.__name__)
            status.status = "failed"

    return wrapper


class SelfTest(Service):
    def __init__(self, application: Application):
        self.application = application
        self.statuses: list[Status] = []

    def shutdown(self):
        pass

    def init(self, gtk_app):
        windows_console_output_workaround()
        self.init_timer(gtk_app, timeout=20)
        self.test_library_versions()
        self.test_new_session()
        if not (
            os.getenv("CI")
            and sys.platform == "darwin"
            and Gtk.get_major_version() == 4
        ):
            # Skip this test for Darwin in CI (GTK 4.8): it's causing
            # all interaction to freeze. May be fixed in GTK 4.10.
            self.test_file_dialog()
        self.test_auto_layout()

    def init_timer(self, gtk_app, timeout):
        start = time.time()

        def callback():
            if time.time() > start + timeout:
                log.error("Tests timed out")
                gtk_app.exit_code = 1
            elif any(status.in_progress for status in self.statuses):
                return GLib.SOURCE_CONTINUE
            elif all(status.completed for status in self.statuses):
                log.info(
                    "All tests have been completed in %.1fs",
                    time.time() - start,
                )
            else:
                log.error("Not all tests have passed")
                gtk_app.exit_code = 1

            for status in self.statuses:
                log.info(status)

            gtk_app.quit()
            return GLib.SOURCE_REMOVE

        GLib.timeout_add(priority=GLib.PRIORITY_LOW, interval=100, function=callback)

    @test
    def test_library_versions(self, status):
        log.info(
            "System information:\n\n%s", textwrap.indent(system_information(), "\t")
        )
        status.complete()

    @test
    def test_new_session(self, status):
        with (importlib.resources.files("gaphor") / "templates" / "uml.gaphor").open(
            encoding="utf-8"
        ) as f:
            session = self.application.new_session(template=f)

        def check_new_session(session):
            main_window = session.get_service("main_window")

            if main_window.window and main_window.window.get_visible():
                status.complete()
                return GLib.SOURCE_REMOVE
            else:
                return GLib.SOURCE_CONTINUE

        GLib.idle_add(check_new_session, session, priority=GLib.PRIORITY_LOW)

    @test
    def test_file_dialog(self, status):
        session = self.application.new_session()
        file_manager = session.get_service("file_manager")
        dialog = file_manager.action_save_as()
        assert dialog

        def check_file_dialog(dialog):
            if dialog.get_visible():
                status.complete()
                return GLib.SOURCE_REMOVE
            else:
                return GLib.SOURCE_CONTINUE

        GLib.idle_add(check_file_dialog, dialog, priority=GLib.PRIORITY_LOW)

    @test
    def test_auto_layout(self, status):
        session = self.application.new_session()
        event_manager = session.get_service("event_manager")
        element_factory = session.get_service("element_factory")
        auto_layout = session.get_service("auto_layout")

        with Transaction(event_manager):
            diagram = element_factory.create(Diagram)

        auto_layout.layout(diagram)
        status.complete()


def system_information():
    return textwrap.dedent(
        f"""\
        Gaphor version:    {distribution().version}
        Operating System:  {platform.system()} ({platform.release()})
        Python version:    {platform.python_version()}
        GTK version:       {Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}
        Adwaita version:   {adwaita_version()}
        PyGObject version: {".".join(map(str, gi.version_info))}
        Pycairo version:   {cairo.version}
        Cairo version:     {cairo.cairo_version_string()}
        Pango version:     {Pango.version_string()}
        Display:           {display_type()}
        """
    )


def adwaita_version():
    if Gtk.get_major_version() == 3:
        return "n.a."

    from gi.repository import Adw

    return (
        f"{Adw.get_major_version()}.{Adw.get_minor_version()}.{Adw.get_micro_version()}"
    )


def display_type():
    dm = Gdk.DisplayManager.get()
    display = dm.get_default_display()
    return display.__class__.__name__ if display else "none"


def windows_console_output_workaround():
    if sys.platform == "win32":
        from gaphor.ui import LOG_FORMAT

        logging.basicConfig(
            level=logging.INFO,
            format=LOG_FORMAT,
            filename="gaphor-self-test.txt",
            filemode="w",
            force=True,
            encoding="utf-8",
        )
