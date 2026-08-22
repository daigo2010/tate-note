"""Which palette the editor draws with, and which one the desktop is asking for.

The editor paints its own page rather than taking colours from the GTK theme,
so a dark desktop needs a palette of its own. Both are warm rather than neutral:
the light one is paper, and the dark one is the same page under a lamp, not a
black terminal.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, Gio, GLib, GObject

LIGHT = {
    "paper": "#f4f1ea",
    "ink": "#2b2b2b",
    "caret": "#b3401f",
    "line_number": "#b5ac99",
    "marker": "#cbc0a9",
    "space_dot": "#c0b6a0",
    "selection": "#d9cdb4",
    "match": "#e8dfae",
    "match_current": "#f0c98a",
    "memo_bg": "#f4f1ea",
    "memo_fg": "#2b2b2b",
    "heading_bg": "#ebe5d8",
    "heading_fg": "#6f6759",
    "border": "#ddd5c4",
}

DARK = {
    "paper": "#1f1d1a",
    "ink": "#e8e2d6",
    "caret": "#ff7a4d",
    "line_number": "#655d4e",
    "marker": "#504a3e",
    "space_dot": "#5a5346",
    "selection": "#453f30",
    "match": "#544a25",
    "match_current": "#6e5f32",
    "memo_bg": "#1f1d1a",
    "memo_fg": "#e8e2d6",
    "heading_bg": "#2a2723",
    "heading_fg": "#a49a86",
    "border": "#3a352d",
}

THEMES = ("system", "light", "dark")


def rgba(hexcode):
    colour = Gdk.RGBA()
    colour.parse(hexcode)
    return colour


class Palette(GObject.Object):
    """The colours in force. One instance, shared by every view."""

    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self):
        super().__init__()
        self.dark = False
        self.hex = LIGHT
        self._build()

    def _build(self):
        for key, value in self.hex.items():
            setattr(self, key, rgba(value))

    def set_dark(self, dark):
        dark = bool(dark)
        if dark == self.dark:
            return
        self.dark = dark
        self.hex = DARK if dark else LIGHT
        self._build()
        self.emit("changed")


COLOURS = Palette()


class SystemTheme(GObject.Object):
    """Watches the desktop's light/dark preference.

    The XDG appearance portal is the authority here. GTK's
    gtk-application-prefer-dark-theme is not: on a Yaru dark desktop it reads
    False even while the portal reports dark, so it is only a fallback for
    desktops with no portal at all.
    """

    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    NAMESPACE = "org.freedesktop.appearance"
    KEY = "color-scheme"

    def __init__(self):
        super().__init__()
        self._bus = None
        self.prefers_dark = False
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error:
            self._bus = None
        self.prefers_dark = self._read()
        if self._bus is not None:
            self._bus.signal_subscribe(
                "org.freedesktop.portal.Desktop",
                "org.freedesktop.portal.Settings", "SettingChanged",
                "/org/freedesktop/portal/desktop", None,
                Gio.DBusSignalFlags.NONE, self._on_setting_changed)

    def _read(self):
        if self._bus is not None:
            try:
                reply = self._bus.call_sync(
                    "org.freedesktop.portal.Desktop",
                    "/org/freedesktop/portal/desktop",
                    "org.freedesktop.portal.Settings", "ReadOne",
                    GLib.Variant("(ss)", (self.NAMESPACE, self.KEY)),
                    None, Gio.DBusCallFlags.NONE, 1000, None)
                # 0 = no preference, 1 = dark, 2 = light
                return reply.unpack()[0] == 1
            except GLib.Error:
                pass
        return self._from_gtk()

    def _from_gtk(self):
        from gi.repository import Gtk
        settings = Gtk.Settings.get_default()
        if settings is None:
            return False
        if settings.props.gtk_application_prefer_dark_theme:
            return True
        name = settings.props.gtk_theme_name or ""
        return name.lower().endswith("-dark")

    def _on_setting_changed(self, _conn, _sender, _path, _iface, _signal, params):
        namespace, key, value = params.unpack()
        if namespace != self.NAMESPACE or key != self.KEY:
            return
        prefers = value == 1
        if prefers != self.prefers_dark:
            self.prefers_dark = prefers
            self.emit("changed")
