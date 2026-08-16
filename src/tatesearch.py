"""The search bar that sits under a document."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, Gtk


class SearchBar(Gtk.Revealer):
    """Find text in one document, stepping through the matches."""

    __gtype_name__ = "TateSearchBar"

    def __init__(self, view):
        super().__init__()
        self.view = view
        self.set_reveal_child(False)

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bar.add_css_class("tate-memo-heading")
        for edge in ("top", "bottom", "start", "end"):
            getattr(bar, "set_margin_" + edge)(4)

        self.entry = Gtk.SearchEntry()
        self.entry.set_placeholder_text("検索")
        self.entry.set_hexpand(True)
        self.entry.connect("search-changed", lambda _e: self.refresh(move=True))
        self.entry.connect("activate", lambda _e: self.step(1))
        self.entry.connect("stop-search", lambda _e: self.close())
        bar.append(self.entry)

        self.status = Gtk.Label(label="")
        self.status.add_css_class("dim-label")
        self.status.set_width_chars(7)
        bar.append(self.status)

        self.case_button = Gtk.ToggleButton(label="Aa")
        self.case_button.set_tooltip_text("大文字と小文字を区別")
        self.case_button.connect("toggled", lambda _b: self.refresh(move=False))
        bar.append(self.case_button)

        for icon, tip, step in (("go-up-symbolic", "前を検索 (Shift+Enter)", -1),
                                ("go-down-symbolic", "次を検索 (Enter)", 1)):
            button = Gtk.Button(icon_name=icon)
            button.set_tooltip_text(tip)
            button.connect("clicked", lambda _b, s=step: self.step(s))
            bar.append(button)

        close = Gtk.Button(icon_name="window-close-symbolic")
        close.set_tooltip_text("閉じる (Esc)")
        close.connect("clicked", lambda _b: self.close())
        bar.append(close)

        # Shift+Enter steps backwards; Escape gives the text back its focus.
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.entry.add_controller(keys)

        self.set_child(bar)

    # ---- driving the search ---------------------------------------------

    @property
    def query(self):
        return self.entry.get_text()

    def open(self):
        """Show the bar, seeded with the selection if there is one."""
        selected = self.view.selected_text()
        if selected and "\n" not in selected:
            self.entry.set_text(selected)
        self.set_reveal_child(True)
        self.entry.grab_focus()
        self.entry.select_region(0, -1)
        self.refresh(move=True)

    def close(self):
        self.set_reveal_child(False)
        self.view.clear_search()
        self.view.grab_focus()

    def refresh(self, move=False):
        """Re-run the search - after typing, or after the text changed."""
        if not self.get_reveal_child():
            return
        count = self.view.find(self.query, self.case_button.get_active())
        if not self.query:
            self.status.set_text("")
            return
        if count == 0:
            self.status.set_text("0件")
            return
        if move:
            self.view.select_match(self.view.match_after_caret())
        elif self.view.current_match < 0:
            self.view.select_match(0)
        self._update_status()

    def step(self, direction):
        if not self.view.matches:
            self.refresh(move=True)
            return
        current = self.view.current_match
        if current < 0:
            current = self.view.match_after_caret(backwards=direction < 0)
            self.view.select_match(current)
        else:
            self.view.select_match(current + direction)
        self._update_status()

    def _update_status(self):
        total = len(self.view.matches)
        if total == 0:
            self.status.set_text("0件")
        else:
            self.status.set_text("{}/{}".format(self.view.current_match + 1, total))

    def _on_key(self, _controller, keyval, _keycode, state):
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_ISO_Enter):
            self.step(-1 if state & Gdk.ModifierType.SHIFT_MASK else 1)
            return True
        return False
