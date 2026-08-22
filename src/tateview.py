"""The vertical text view widget.

It owns every mark on the page - text, caret, line numbers, whitespace markers -
so none of them can disturb any of the others, and it owns the editing model, so
the caret is always exactly where we put it.

Caret positions are held as *character* indices and converted to the byte
indices Pango wants only at the boundary; that keeps multi-byte text from ever
landing mid-character.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Pango", "1.0")

from gi.repository import GLib, GObject, Gdk, Gtk, Graphene, Pango

from tatelayout import VerticalLayout, DEFAULT_FONT
from tatetheme import COLOURS
from tateundo import Edit, UndoStack


class VerticalTextView(Gtk.Widget):
    """Vertical text, drawn and edited by us."""

    __gtype_name__ = "VerticalTextView"

    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, text=""):
        super().__init__()
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_focusable(True)
        self.set_can_focus(True)

        self._text = text
        self._caret = 0                 # character index
        self._anchor = None             # selection anchor, character index
        self._preedit = ""
        self._preedit_attrs = None
        self._preedit_caret = 0
        self._doc = VerticalLayout(text)
        self._show_line_numbers = False
        self._show_whitespace = False
        self._matches = []              # (start, end) character indices
        self._current_match = -1
        self._scroll = 0.0
        self._undo = UndoStack()

        self._im = Gtk.IMMulticontext()
        self._im.set_client_widget(self)
        self._im.connect("commit", self._on_commit)
        self._im.connect("preedit-changed", self._on_preedit_changed)
        self._im.connect("preedit-end", self._on_preedit_end)

        keys = Gtk.EventControllerKey()
        keys.set_im_context(self._im)
        keys.connect("key-pressed", self._on_key_pressed)
        self.add_controller(keys)

        focus = Gtk.EventControllerFocus()
        focus.connect("enter", lambda *_a: self._im.focus_in())
        focus.connect("leave", lambda *_a: self._im.focus_out())
        self.add_controller(focus)

        click = Gtk.GestureClick()
        click.connect("pressed", self._on_pressed)
        self.add_controller(click)

        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        self.add_controller(drag)

        # Scrolling is ours too. A GtkScrolledWindow would have to be told the
        # document's natural width and then be persuaded to start at the right
        # edge; owning the offset directly is simpler and matches the drawing.
        scroll = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.BOTH_AXES)
        scroll.connect("scroll", self._on_scroll)
        self.add_controller(scroll)

        self._adjustment = Gtk.Adjustment()
        self._adjustment.connect("value-changed", self._on_adjustment)

        self._sync()

    # ---- scrolling -------------------------------------------------------

    @property
    def adjustment(self):
        """Drives an external scrollbar; value counts pixels into the text."""
        return self._adjustment

    def _visible_across(self):
        return max(1.0, self.get_width() - 2 * self._doc.padding_block)

    def _content_across(self):
        _along, across = self._doc.size_px()
        return across

    def _max_scroll(self):
        return max(0.0, self._content_across() - self._visible_across())

    def set_scroll(self, value):
        value = max(0.0, min(float(value), self._max_scroll()))
        if abs(value - self._scroll) < 0.01:
            return
        self._scroll = value
        if abs(self._adjustment.get_value() - value) > 0.01:
            self._adjustment.set_value(value)
        self.queue_draw()

    def _refresh_adjustment(self):
        span = self._visible_across()
        self._adjustment.configure(
            min(self._scroll, self._max_scroll()), 0.0,
            max(self._content_across(), span),
            self._doc.column_pitch, span * 0.9, span)

    def _on_adjustment(self, adj):
        self.set_scroll(adj.get_value())

    def _on_scroll(self, _controller, dx, dy):
        # Either wheel axis walks the document; vertical-rl reads leftwards, so
        # scrolling "down" moves further in.
        self.set_scroll(self._scroll + (dy + dx) * self._doc.column_pitch)
        return True

    def scroll_by_page(self, pages):
        """One screenful further into the text (+1) or back towards it (-1)."""
        self.set_scroll(self._scroll + pages * self._visible_across())

    def scroll_caret_into_view(self):
        """Shift just enough for the caret's column to be fully visible."""
        _x, y, _w, h = self._doc.caret_rect(self._byte(self._caret))
        near, far = y, y + h           # distance into the text, from column one
        if far > self._scroll + self._visible_across():
            self.set_scroll(far - self._visible_across())
        elif near < self._scroll:
            self.set_scroll(near)

    # ---- document --------------------------------------------------------

    @property
    def text(self):
        """The document, never including any in-flight preedit."""
        return self._text

    def set_text(self, text):
        """Load a document. This is not an edit, so it starts history over."""
        self._text = text
        self._caret = min(self._caret, len(text))
        self._anchor = None
        self._undo.reset()
        self._sync()
        self.emit("changed")

    @property
    def caret_index(self):
        return self._caret

    def set_caret_index(self, index, extend=False):
        # Deliberately moving the caret ends whatever was being typed, so the
        # next keystroke starts its own undo step.
        self._undo.barrier()
        if extend:
            if self._anchor is None:
                self._anchor = self._caret
        else:
            self._anchor = None
        self._caret = max(0, min(int(index), len(self._text)))
        self._sync()
        if self.get_width() > 0:
            self.scroll_caret_into_view()

    # ---- search ----------------------------------------------------------

    @property
    def matches(self):
        return list(self._matches)

    @property
    def current_match(self):
        return self._current_match

    def find(self, query, case_sensitive=False):
        """Locate every occurrence; returns how many there are."""
        self._matches = []
        self._current_match = -1
        if query:
            self._matches = self._scan(query, case_sensitive)
        self.queue_draw()
        return len(self._matches)

    def _scan(self, query, case_sensitive):
        text = self._text
        span = len(query)
        if case_sensitive:
            found, start = [], 0
            while True:
                at = text.find(query, start)
                if at < 0:
                    break
                found.append((at, at + span))
                start = at + span
            return found
        lowered = text.lower()
        if len(lowered) == len(text):
            # Same length, so positions in the folded copy still address the
            # original text and the fast path is safe.
            needle, found, start = query.lower(), [], 0
            while True:
                at = lowered.find(needle, start)
                if at < 0:
                    break
                found.append((at, at + span))
                start = at + span
            return found
        # Rare scripts fold to a different length; compare slice by slice so the
        # indices keep pointing at the real characters.
        needle, found, i = query.lower(), [], 0
        while i <= len(text) - span:
            if text[i:i + span].lower() == needle:
                found.append((i, i + span))
                i += span
            else:
                i += 1
        return found

    def select_match(self, index):
        """Show one match: select it, and bring it into view."""
        if not self._matches:
            return
        index %= len(self._matches)
        self._current_match = index
        start, end = self._matches[index]
        self._anchor = start
        self._caret = end
        self._sync()
        self.scroll_caret_into_view()

    def match_after_caret(self, backwards=False):
        """Index of the match nearest the caret, for starting a search there."""
        if not self._matches:
            return -1
        if backwards:
            for i in range(len(self._matches) - 1, -1, -1):
                if self._matches[i][0] < self._caret:
                    return i
            return len(self._matches) - 1
        for i, (start, _end) in enumerate(self._matches):
            if start >= self._caret:
                return i
        return 0

    def clear_search(self):
        self._matches = []
        self._current_match = -1
        self.queue_draw()

    # ---- selection -------------------------------------------------------

    @property
    def selection(self):
        """(start, end) character indices, or None."""
        if self._anchor is None or self._anchor == self._caret:
            return None
        return tuple(sorted((self._anchor, self._caret)))

    def select_all(self):
        self._anchor = 0
        self._caret = len(self._text)
        self._sync()

    def selected_text(self):
        span = self.selection
        return self._text[span[0]:span[1]] if span else ""

    def delete_selection(self):
        span = self.selection
        if not span:
            return False
        # Removing a selection is a decision in itself: sealed off on both sides
        # so neither the backspacing before it nor the backspacing after it gets
        # folded into the same step.
        self._undo.barrier()
        removed = self.replace_span(span[0], span[1], "")
        self._undo.barrier()
        return removed

    def _display_text(self):
        return self._text[:self._caret] + self._preedit + self._text[self._caret:]

    def _byte(self, char_index, text=None):
        source = self._text if text is None else text
        return len(source[:char_index].encode("utf-8"))

    # The long bars are rotated a quarter turn like Latin, but unlike a word
    # they should sit centred in their cell. Under the natural gravity hint they
    # come out a few percent of an em towards the left of the column; a strong
    # hint on just these characters centres them without dragging Latin words
    # upright with it.
    CENTRED_MARKS = "ー＝〜―‐－"

    def _sync(self):
        """Push the document (plus any preedit) into the layout."""
        display = self._display_text()
        self._doc.set_text(display)
        attrs = Pango.AttrList()
        offset = 0
        for ch in display:
            span = len(ch.encode("utf-8"))
            if ch in self.CENTRED_MARKS:
                hint = Pango.attr_gravity_hint_new(Pango.GravityHint.STRONG)
                hint.start_index = offset
                hint.end_index = offset + span
                attrs.insert(hint)
            offset += span
        if self._preedit and self._preedit_attrs is not None:
            # Shift the IM's attributes to where the preedit actually sits.
            offset = self._byte(self._caret)
            it = self._preedit_attrs.get_iterator()
            while True:
                for attr in it.get_attrs():
                    moved = attr.copy()
                    moved.start_index += offset
                    moved.end_index += offset
                    attrs.insert(moved)
                if not it.next():
                    break
        self._doc.layout.set_attributes(attrs)
        if self.get_width() > 0:
            self._refresh_adjustment()
        self.queue_draw()

    # ---- editing ---------------------------------------------------------

    def _apply(self, start, end, chunk, caret, anchor):
        """Swap one span of text and put the caret down. Records nothing."""
        self._text = self._text[:start] + chunk + self._text[end:]
        self._caret = max(0, min(caret, len(self._text)))
        self._anchor = None if anchor is None else max(0, min(anchor, len(self._text)))
        self._sync()
        self.emit("changed")

    def replace_span(self, start, end, chunk):
        """The single way the document ever changes, so nothing escapes undo."""
        removed = self._text[start:end]
        if not removed and not chunk:
            return False
        after = (start + len(chunk), None)
        self._undo.record(
            Edit(start, removed, chunk, (self._caret, self._anchor), after))
        self._apply(start, end, chunk, *after)
        return True

    def insert(self, chunk):
        if not chunk:
            return
        span = self.selection            # typing replaces the selection
        if span:
            self._undo.barrier()
            self.replace_span(span[0], span[1], chunk)
        else:
            self.replace_span(self._caret, self._caret, chunk)

    def delete_before(self):
        if self.delete_selection():
            return
        if self._caret <= 0:
            return
        self.replace_span(self._caret - 1, self._caret, "")

    def delete_after(self):
        if self.delete_selection():
            return
        if self._caret >= len(self._text):
            return
        self.replace_span(self._caret, self._caret + 1, "")

    # ---- undo ------------------------------------------------------------

    @property
    def can_undo(self):
        return self._undo.can_undo

    @property
    def can_redo(self):
        return self._undo.can_redo

    def undo(self):
        edit = self._undo.undo()
        if edit is None:
            return False
        self._apply(edit.start, edit.end, edit.removed, *edit.before)
        return True

    def redo(self):
        edit = self._undo.redo()
        if edit is None:
            return False
        self._apply(edit.start, edit.start + len(edit.removed), edit.inserted,
                    *edit.after)
        return True

    # ---- replacing -------------------------------------------------------

    def replace_current(self, replacement):
        """Swap the match the selection is sitting on. True if one was."""
        if not 0 <= self._current_match < len(self._matches):
            return False
        span = self._matches[self._current_match]
        if self.selection != span:
            return False                 # the caret has moved off the match
        self._undo.barrier()
        self.replace_span(span[0], span[1], replacement)
        self._undo.barrier()
        return True

    def replace_all(self, query, replacement, case_sensitive=False):
        """Swap every occurrence as one undo step; returns how many there were.

        The whole run from the first match to the last is rewritten in a single
        replacement so that undo puts the document back in one press.
        """
        spans = self._scan(query, case_sensitive) if query else []
        if not spans:
            return 0
        start, end = spans[0][0], spans[-1][1]
        pieces, at = [], start
        for match_start, match_end in spans:
            pieces.append(self._text[at:match_start])
            pieces.append(replacement)
            at = match_end
        self._undo.barrier()
        self.replace_span(start, end, "".join(pieces))
        self._undo.barrier()
        return len(spans)

    # ---- clipboard -------------------------------------------------------

    def copy_selection(self):
        chunk = self.selected_text()
        if chunk:
            self.get_clipboard().set(chunk)
        return bool(chunk)

    def cut_selection(self):
        if self.copy_selection():
            self.delete_selection()
            return True
        return False

    def paste_clipboard(self):
        def done(clipboard, result):
            try:
                chunk = clipboard.read_text_finish(result)
            except GLib.Error:
                return
            if chunk:
                self.insert(chunk.replace("\r\n", "\n").replace("\r", "\n"))
        self.get_clipboard().read_text_async(None, done)

    # ---- input -----------------------------------------------------------

    def _on_commit(self, _im, chunk):
        self._preedit = ""
        self._preedit_attrs = None
        self.insert(chunk)

    def _on_preedit_changed(self, im):
        self._preedit, self._preedit_attrs, self._preedit_caret = \
            im.get_preedit_string()
        self._sync()

    def _on_preedit_end(self, _im):
        self._preedit = ""
        self._preedit_attrs = None
        self._sync()

    def _on_key_pressed(self, _controller, keyval, _keycode, state):
        if self._preedit:
            return False                # let the IM own the keystroke
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)

        if ctrl:
            lower = Gdk.keyval_to_unicode(Gdk.keyval_to_lower(keyval))
            letter = chr(lower) if lower else ""
            if letter == "a":
                self.select_all(); return True
            if letter == "c":
                self.copy_selection(); return True
            if letter == "x":
                self.cut_selection(); return True
            if letter == "v":
                self.paste_clipboard(); return True
            if letter == "z":
                self.redo() if shift else self.undo()
                return True
            if letter == "y":
                self.redo(); return True
            if keyval in (Gdk.KEY_Home, Gdk.KEY_KP_Home):
                self.set_caret_index(0)
                return True
            if keyval in (Gdk.KEY_End, Gdk.KEY_KP_End):
                self.set_caret_index(len(self._text))
                return True
            return False                # file shortcuts belong to the window

        # Visual directions: down/up walk the column, left/right change column.
        moves = {
            Gdk.KEY_Down: ("char", 1), Gdk.KEY_Up: ("char", -1),
            Gdk.KEY_Left: ("line", 1), Gdk.KEY_Right: ("line", -1),
        }
        if keyval in moves:
            self.move_caret(*moves[keyval], extend=shift)
            return True
        if keyval in (Gdk.KEY_BackSpace,):
            self.delete_before(); return True
        if keyval in (Gdk.KEY_Delete, Gdk.KEY_KP_Delete):
            self.delete_after(); return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_ISO_Enter):
            self.insert("\n"); return True
        if keyval == Gdk.KEY_Tab:
            self.insert("\t"); return True
        # Ctrl jumps to the ends of the document, above; plain Home/End stay on
        # the current line.
        if keyval in (Gdk.KEY_Home, Gdk.KEY_KP_Home):
            self.set_caret_index(self._line_bounds()[0])
            return True
        if keyval in (Gdk.KEY_End, Gdk.KEY_KP_End):
            self.set_caret_index(self._line_bounds()[1])
            return True
        # Paging scrolls the view; the caret stays where it was.
        if keyval in (Gdk.KEY_Page_Down, Gdk.KEY_KP_Page_Down):
            self.scroll_by_page(1); return True
        if keyval in (Gdk.KEY_Page_Up, Gdk.KEY_KP_Page_Up):
            self.scroll_by_page(-1); return True
        return False                    # anything else goes to the IM

    def _on_pressed(self, _gesture, _n_press, x, y):
        self.grab_focus()
        self.place_caret_at(x, y)

    def _on_drag_begin(self, _gesture, x, y):
        self.grab_focus()
        self.place_caret_at(x, y)
        self._anchor = self._caret       # start of a drag selection
        self._drag_origin = (x, y)

    def _on_drag_update(self, _gesture, dx, dy):
        origin = getattr(self, "_drag_origin", None)
        if origin is None:
            return
        self.place_caret_at(origin[0] + dx, origin[1] + dy, extend=True)

    def _line_bounds(self):
        start = self._text.rfind("\n", 0, self._caret) + 1
        end = self._text.find("\n", self._caret)
        return start, (len(self._text) if end < 0 else end)

    # ---- caret -----------------------------------------------------------

    def move_caret(self, kind, direction, extend=False):
        """One character along the column, or one column across."""
        if kind == "char":
            self.set_caret_index(self._caret + direction, extend=extend)
            return
        # Across columns: aim at the middle of the neighbouring line box. The
        # gap between columns belongs to no line, so stepping by a guessed pitch
        # just snaps back to where it started.
        x, _y, _w, _h = self._doc.caret_rect(self._byte(self._caret))
        boxes = self._doc.line_boxes()
        target = self._doc.visual_line_of(self._byte(self._caret)) + direction
        if not 0 <= target < len(boxes):
            return
        _bx, by, _bw, bh = boxes[target]
        index, trailing = self._doc.index_at(x, by + bh / 2.0)
        self.set_caret_index(self._chars_for_byte(index) + trailing, extend=extend)

    def place_caret_at(self, widget_x, widget_y, extend=False):
        origin_x, origin_y = self._origin(self.get_width())
        # Undo the quarter turn: screen x runs leftwards into the columns.
        layout_x = widget_y - origin_y
        layout_y = (origin_x + self._scroll) - widget_x
        index, trailing = self._doc.index_at(layout_x, layout_y)
        self.set_caret_index(self._chars_for_byte(index) + trailing, extend=extend)

    def _chars_for_byte(self, byte_index):
        raw = self._display_text().encode("utf-8")[:max(0, byte_index)]
        return len(raw.decode("utf-8", "ignore"))

    # ---- display options -------------------------------------------------

    def set_font_size(self, size):
        self._doc.set_size(size)
        self._sync()

    @property
    def font_size(self):
        return self._doc.size

    def set_show_line_numbers(self, on):
        self._show_line_numbers = bool(on)
        self.queue_draw()

    def set_show_whitespace(self, on):
        self._show_whitespace = bool(on)
        self.queue_draw()

    # ---- geometry --------------------------------------------------------

    def do_size_allocate(self, width, height, _baseline):
        # Reflow and republish the scroll range here rather than while drawing:
        # touching the adjustment mid-snapshot makes the scrollbar restyle in
        # the middle of the frame, before it has an allocation.
        self._reflow(width, height)
        self._refresh_adjustment()

    def do_measure(self, orientation, _for_size):
        # The widget fills the window; the document scrolls inside it.
        minimum = int(self._doc.em * 8)
        return (minimum, minimum, -1, -1)

    def caret_screen_span(self):
        """Where the caret is horizontally on screen, as (left, right)."""
        origin_x, _origin_y = self._origin(self.get_width())
        _x, y, _w, h = self._doc.caret_rect(self._byte(self._caret))
        right = origin_x + self._scroll - y
        return right - h, right

    def _gutter(self):
        if not self._show_line_numbers:
            return 0.0
        digits = len(str(max(1, self._text.count("\n") + 1)))
        return self._doc.em * (0.42 * digits + 0.35)

    def _reflow(self, _width, height):
        usable = height - 2 * self._doc.padding_inline - self._gutter()
        self._doc.set_column_length(max(self._doc.em, usable))

    def _origin(self, width):
        return (width - self._doc.padding_block,
                self._doc.padding_inline + self._gutter())

    # ---- painting --------------------------------------------------------

    def do_snapshot(self, snapshot):
        width = self.get_width()
        height = self.get_height()
        if width <= 0 or height <= 0:
            return

        self._reflow(width, height)
        snapshot.append_color(COLOURS.paper, Graphene.Rect().init(0, 0, width, height))

        origin_x, origin_y = self._origin(width)
        snapshot.save()
        snapshot.translate(Graphene.Point().init(origin_x + self._scroll, origin_y))
        snapshot.rotate(90.0)

        self._draw_matches(snapshot)
        self._draw_selection(snapshot)
        if self._show_whitespace:
            self._draw_whitespace(snapshot)
        snapshot.append_layout(self._doc.layout, COLOURS.ink)
        self._draw_caret(snapshot)

        snapshot.restore()

        # Line numbers live outside the turned canvas, in screen coordinates, so
        # the digits stand upright and nothing here can perturb the text.
        if self._show_line_numbers:
            self._draw_line_numbers(snapshot, origin_x, origin_y)

    def _draw_matches(self, snapshot):
        for index, (start, end) in enumerate(self._matches):
            colour = COLOURS.match_current if index == self._current_match else COLOURS.match
            for x, y, w, h in self._doc.selection_rects(self._byte(start),
                                                        self._byte(end)):
                snapshot.append_color(colour, Graphene.Rect().init(x, y, w, h))

    def _draw_selection(self, snapshot):
        span = self.selection
        if not span:
            return
        start, end = span
        for x, y, w, h in self._doc.selection_rects(self._byte(start), self._byte(end)):
            snapshot.append_color(COLOURS.selection, Graphene.Rect().init(x, y, w, h))

    def _draw_caret(self, snapshot):
        index = self._byte(self._caret) + len(
            self._preedit[:self._preedit_caret].encode("utf-8"))
        x, y, w, h = self._doc.caret_rect(index)
        snapshot.append_color(COLOURS.caret, Graphene.Rect().init(x, y, max(w, 2.0), h))

    def _number_layout(self, text, size):
        layout = Pango.Layout.new(self.get_pango_context())
        desc = Pango.FontDescription(DEFAULT_FONT)
        desc.set_absolute_size(int(size * Pango.SCALE))
        layout.set_font_description(desc)
        layout.set_text(text, -1)
        return layout

    def _draw_line_numbers(self, snapshot, origin_x, origin_y):
        gutter = self._gutter()
        if gutter <= 0:
            return
        size = self._doc.em * 0.62
        boxes = self._doc.line_boxes()
        # Logical lines, not wrapped columns: a paragraph spilling over several
        # columns keeps one number.
        for number, start in enumerate(self._doc.logical_line_starts(), 1):
            visual = self._doc.visual_line_of(start)
            if visual >= len(boxes):
                continue
            _lx, ly, _lw, lh = boxes[visual]
            layout = self._number_layout(str(number), size)
            width, height = layout.get_pixel_size()
            centre_x = (origin_x + self._scroll - ly) - lh / 2.0
            snapshot.save()
            snapshot.translate(Graphene.Point().init(
                centre_x - width / 2.0, origin_y - gutter + (gutter - height) / 2.0))
            snapshot.append_layout(layout, COLOURS.line_number)
            snapshot.restore()

    def _draw_whitespace(self, snapshot):
        display = self._display_text()
        index = 0
        for ch in display:
            span = len(ch.encode("utf-8"))
            if ch == "\n":
                x, y, _w, h = self._doc.caret_rect(index)
                arm = self._doc.em * 0.30
                snapshot.append_color(
                    COLOURS.marker, Graphene.Rect().init(x, y + h * 0.5 - 1, arm, 2))
                snapshot.append_color(
                    COLOURS.marker, Graphene.Rect().init(x + arm - 2, y + h * 0.5 - 1, 2, arm))
            elif ch in (" ", "　", "\t"):
                x, y, _w, h = self._doc.caret_rect(index)
                nx, _ny, _nw, _nh = self._doc.caret_rect(index + span)
                length = max(nx - x, 2.0)
                if ch == "\t":
                    snapshot.append_color(
                        COLOURS.marker, Graphene.Rect().init(x, y + h / 2 - 1, length, 2))
                elif ch == "　":
                    self._stroke_rect(snapshot, x + 1, y + 2, length - 2, h - 4)
                else:
                    snapshot.append_color(
                        COLOURS.space_dot,
                        Graphene.Rect().init(x + length / 2 - 1.5, y + h / 2 - 1.5, 3, 3))
            index += span

    def _stroke_rect(self, snapshot, x, y, w, h):
        for rect in ((x, y, w, 1), (x, y + h - 1, w, 1),
                     (x, y, 1, h), (x + w - 1, y, 1, h)):
            snapshot.append_color(COLOURS.marker, Graphene.Rect().init(*rect))
