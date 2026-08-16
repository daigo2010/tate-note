"""The search and replace bar that sits under a document."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, Gtk


class SearchBar(Gtk.Revealer):
    """Find text in one document, step through the matches, replace them."""

    __gtype_name__ = "TateSearchBar"

    def __init__(self, view):
        super().__init__()
        self.view = view
        self.set_reveal_child(False)

        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        rows.add_css_class("tate-memo-heading")
        for edge in ("top", "bottom", "start", "end"):
            getattr(rows, "set_margin_" + edge)(4)

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

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

        self.replace_button = Gtk.ToggleButton(icon_name="edit-find-replace-symbolic")
        self.replace_button.set_tooltip_text("置換 (Ctrl+H)")
        self.replace_button.connect("toggled", self._on_replace_toggled)
        bar.append(self.replace_button)

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

        rows.append(bar)
        rows.append(self._build_replace_row())
        self.set_child(rows)

    def _build_replace_row(self):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.set_visible(False)

        self.replace_entry = Gtk.Entry()
        self.replace_entry.set_placeholder_text("置換後の文字列")
        self.replace_entry.set_hexpand(True)
        self.replace_entry.connect("activate", lambda _e: self.replace_one())
        row.append(self.replace_entry)

        for label, tip, handler in (
                ("置換", "この一致を置換 (Enter)", self.replace_one),
                ("すべて置換", "すべての一致を置換", self.replace_all)):
            button = Gtk.Button(label=label)
            button.set_tooltip_text(tip)
            button.connect("clicked", lambda _b, fn=handler: fn())
            row.append(button)

        # Escape closes from here too, so the bar behaves the same either row.
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_replace_key)
        self.replace_entry.add_controller(keys)

        self.replace_row = row
        return row

    def _on_replace_toggled(self, button):
        self.replace_row.set_visible(button.get_active())
        if button.get_active():
            self.replace_entry.grab_focus()

    # ---- driving the search ---------------------------------------------

    @property
    def query(self):
        return self.entry.get_text()

    @property
    def replacement(self):
        return self.replace_entry.get_text()

    def open(self, replace=False):
        """Show the bar, seeded with the selection if there is one."""
        selected = self.view.selected_text()
        if selected and "\n" not in selected:
            self.entry.set_text(selected)
        self.set_reveal_child(True)
        if replace:
            self.replace_button.set_active(True)
        self.entry.grab_focus()
        self.entry.select_region(0, -1)
        self.refresh(move=True)

    def close(self):
        self.set_reveal_child(False)
        self.view.clear_search()
        self.view.grab_focus()

    def refresh(self, move=False):
        """Re-run the search - after typing, or after the text changed.

        Only an explicit `move` takes the caret anywhere. Editing the document
        re-runs this, and a writer typing with the bar open should not be hauled
        off to the first match.
        """
        if not self.get_reveal_child():
            return
        count = self.view.find(self.query, self.case_button.get_active())
        if not self.query:
            self.status.set_text("")
            return
        if count and move:
            self.view.select_match(self.view.match_after_caret())
        self._update_status()

    # ---- replacing -------------------------------------------------------

    def replace_one(self):
        """Replace the match currently shown, then go on to the next."""
        if not self.query:
            return
        if not self.view.replace_current(self.replacement):
            self.step(1)                 # nothing selected yet - show one first
            return
        self.refresh(move=True)

    def replace_all(self):
        if not self.query:
            return
        count = self.view.replace_all(self.query, self.replacement,
                                      self.case_button.get_active())
        self.refresh()
        self.status.set_text("{}件置換".format(count) if count else "0件")

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
        elif self.view.current_match < 0:
            # Found, but the caret is not on any of them.
            self.status.set_text("{}件".format(total))
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

    def _on_replace_key(self, _controller, keyval, _keycode, _state):
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False
