"""One open document: the view, its scrollbar, and what file it came from."""

import os

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import GObject, Gtk

from tateview import VerticalTextView


class Document(Gtk.Box):
    """A tab's contents. Owns its own text, caret, scroll position and file."""

    __gtype_name__ = "TateDocument"

    __gsignals__ = {
        # Anything that could change the tab label or the header.
        "state-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.path = None
        self.modified = False

        self.view = VerticalTextView("")
        self.view.connect("changed", self._on_changed)

        # vertical-rl grows leftwards, so the document scrolls horizontally and
        # the scrollbar is flipped: column one lives at the right-hand end.
        self.scrollbar = Gtk.Scrollbar(orientation=Gtk.Orientation.HORIZONTAL,
                                       adjustment=self.view.adjustment)
        self.scrollbar.set_direction(Gtk.TextDirection.RTL)
        self.view.adjustment.connect("changed", lambda _a: self._sync_scrollbar())

        self.append(self.view)
        self.append(self.scrollbar)
        self._sync_scrollbar()

    # ---- state -----------------------------------------------------------

    @property
    def title(self):
        return os.path.basename(self.path) if self.path else "無題"

    @property
    def label(self):
        return self.title + (" *" if self.modified else "")

    def _on_changed(self, _view):
        if not self.modified:
            self.modified = True
        self.view.scroll_caret_into_view()
        self.emit("state-changed")

    def _sync_scrollbar(self):
        """Dim the scrollbar while the whole document fits.

        It stays mapped either way: the scroll range is refreshed during layout,
        and showing a sibling then would leave it without an allocation.
        """
        adj = self.view.adjustment
        scrollable = adj.get_upper() > adj.get_page_size() + 1
        self.scrollbar.set_sensitive(scrollable)
        self.scrollbar.set_opacity(1.0 if scrollable else 0.0)

    # ---- files -----------------------------------------------------------

    @property
    def is_untouched(self):
        """A blank, never-saved tab - the one worth reusing rather than adding."""
        return self.path is None and not self.modified and not self.view.text

    def load(self, path):
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        self.view.set_text(text.rstrip("\n"))
        self.view.set_caret_index(0)
        self.path = path
        self.modified = False
        self.emit("state-changed")

    def save(self, path=None):
        target = path or self.path
        text = self.view.text
        if text:
            text += "\n"
        with open(target, "w", encoding="utf-8") as f:
            f.write(text)
        self.path = target
        self.modified = False
        self.emit("state-changed")

    def char_count(self, count_newlines):
        text = self.view.text
        if not count_newlines:
            text = text.replace("\n", "")
        return len(text)
