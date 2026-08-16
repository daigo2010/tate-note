"""One open document: the vertical text, its memo, and what file it came from.

Each document also owns a memo - free-form horizontal notes kept beside the
text. On disk the memo lives next to the document under a dot-prefixed name, so
`novel.txt` is accompanied by `.novel.txt`.
"""

import os

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gdk, GObject, Gtk

from tateview import VerticalTextView

MEMO_WIDTH = 240

# The editor draws its own paper; left to the system theme the memo beside it
# would come out dark and the pair would look like two different applications.
MEMO_CSS = b"""
.tate-memo, .tate-memo text {
  background-color: #f4f1ea;
  color: #2b2b2b;
}
.tate-memo-heading {
  background-color: #ebe5d8;
  color: #6f6759;
  font-size: 0.85em;
}
.tate-memo-side {
  border-left: 1px solid #ddd5c4;
}
"""
_css_installed = False


def _install_css():
    global _css_installed
    if _css_installed:
        return
    display = Gdk.Display.get_default()
    if display is None:
        return
    provider = Gtk.CssProvider()
    provider.load_from_data(MEMO_CSS)
    Gtk.StyleContext.add_provider_for_display(
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    _css_installed = True


def memo_path_for(path):
    """`/dir/novel.txt` -> `/dir/.novel.txt`."""
    if not path:
        return None
    directory, name = os.path.split(path)
    return os.path.join(directory, "." + name)


class Document(Gtk.Paned):
    """A tab's contents: the vertical text on the left, the memo on the right."""

    __gtype_name__ = "TateDocument"

    __gsignals__ = {
        # Anything that could change the tab label or the header.
        "state-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
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

        editor = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        editor.append(self.view)
        editor.append(self.scrollbar)
        self.set_start_child(editor)
        self.set_resize_start_child(True)
        self.set_shrink_start_child(False)

        self.set_end_child(self._build_memo())
        self.set_resize_end_child(False)
        self.set_shrink_end_child(False)

        self._sync_scrollbar()

    # ---- memo ------------------------------------------------------------

    def _build_memo(self):
        _install_css()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_size_request(MEMO_WIDTH, -1)
        box.add_css_class("tate-memo-side")

        heading = Gtk.Label(label="メモ", xalign=0.0)
        heading.add_css_class("tate-memo-heading")
        for edge in ("top", "bottom", "start", "end"):
            getattr(heading, "set_margin_" + edge)(6)
        box.append(heading)
        box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # Horizontal writing, as the issue allows - notes are not prose.
        self.memo = Gtk.TextView()
        self.memo.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.memo.set_top_margin(6)
        self.memo.set_bottom_margin(6)
        self.memo.set_left_margin(8)
        self.memo.set_right_margin(8)
        self.memo.add_css_class("tate-memo")
        self.memo.get_buffer().connect("changed", self._on_memo_changed)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroller.set_child(self.memo)
        scroller.set_vexpand(True)
        box.append(scroller)

        self.memo_pane = box
        return box

    @property
    def memo_text(self):
        buffer = self.memo.get_buffer()
        return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)

    def set_memo_text(self, text):
        self._loading_memo = True
        self.memo.get_buffer().set_text(text or "")
        self._loading_memo = False

    def set_show_memo(self, visible):
        self.memo_pane.set_visible(bool(visible))

    def _on_memo_changed(self, _buffer):
        if getattr(self, "_loading_memo", False):
            return
        if not self.modified:
            self.modified = True
        self.emit("state-changed")

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
        return (self.path is None and not self.modified
                and not self.view.text and not self.memo_text)

    def load(self, path):
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        self.view.set_text(text.rstrip("\n"))
        self.view.set_caret_index(0)

        # A memo saved alongside the document comes back with it.
        memo = ""
        companion = memo_path_for(path)
        if companion and os.path.exists(companion):
            try:
                with open(companion, "r", encoding="utf-8") as f:
                    memo = f.read()
            except (OSError, UnicodeDecodeError):
                memo = ""
        self.set_memo_text(memo)

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
        self._save_memo(target)
        self.path = target
        self.modified = False
        self.emit("state-changed")

    def _save_memo(self, target):
        """Write the memo beside the document, or clear it away when empty.

        An emptied memo removes its file rather than leaving stale notes that
        would reappear the next time the document is opened.
        """
        companion = memo_path_for(target)
        if companion is None:
            return
        memo = self.memo_text
        if memo.strip():
            if not memo.endswith("\n"):
                memo += "\n"
            with open(companion, "w", encoding="utf-8") as f:
                f.write(memo)
        elif os.path.exists(companion):
            try:
                os.remove(companion)
            except OSError:
                pass

    def char_count(self, count_newlines):
        text = self.view.text
        if not count_newlines:
            text = text.replace("\n", "")
        return len(text)
