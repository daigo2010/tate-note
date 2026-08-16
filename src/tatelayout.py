"""Vertical (tategaki) text layout on top of Pango.

The whole point of this module is that *we* own the geometry. Pango is asked to
lay the text out along its own x axis with an east gravity, and the widget then
turns the canvas a quarter turn so that axis runs down the page and successive
lines march leftwards - that is vertical-rl. Because every position we need
(caret, line boxes, hit testing) comes back from Pango as a number, nothing
about the presentation is left to somebody else's editing engine.
"""

import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")

from gi.repository import Pango, PangoCairo

SCALE = Pango.SCALE

DEFAULT_FONT = "Noto Serif CJK JP, IPAmincho, Hiragino Mincho ProN, serif"
DEFAULT_SIZE = 22.0          # px, matching the previous editor
LINE_SPACING = 2.0           # column pitch in ems, i.e. CSS line-height: 2
PAD_INLINE = 2.5             # ems of space before the first character
PAD_BLOCK = 1.5              # ems of space before the first column


def _pango_units(value):
    return int(round(value * SCALE))


class VerticalLayout:
    """A Pango layout configured for vertical Japanese text.

    Coordinates handed back are *layout* coordinates: x runs along the column
    (down the page once the canvas is turned) and y runs across the columns
    (leftwards on screen).
    """

    def __init__(self, text="", font=DEFAULT_FONT, size=DEFAULT_SIZE):
        self._font = font
        self._size = size
        self._column_length = 0
        self._context = PangoCairo.FontMap.get_default().create_context()
        self._context.set_base_gravity(Pango.Gravity.EAST)
        # NATURAL keeps kana and kanji upright while rotating the scripts that
        # are meant to lie on their side.
        self._context.set_gravity_hint(Pango.GravityHint.NATURAL)
        self._layout = Pango.Layout.new(self._context)
        self._layout.set_wrap(Pango.WrapMode.CHAR)
        self._layout.set_line_spacing(LINE_SPACING)
        self._apply_font()
        self.set_text(text)

    # ---- configuration ---------------------------------------------------

    def _apply_font(self):
        desc = Pango.FontDescription(self._font)
        desc.set_absolute_size(_pango_units(self._size))
        self._context.set_font_description(desc)
        self._layout.set_font_description(desc)
        # set_line_spacing() multiplies the *font's* natural line height, which
        # is not the same as CSS line-height. Measure the natural height and add
        # absolute spacing instead, so a column is exactly LINE_SPACING ems wide
        # and matches the look of the previous build.
        self._layout.set_line_spacing(0.0)
        self._layout.set_spacing(0)
        probe = Pango.Layout.new(self._context)
        probe.set_font_description(desc)
        probe.set_text("あ", -1)
        _w, natural = probe.get_size()
        natural /= SCALE
        extra = LINE_SPACING * self._size - natural
        self._layout.set_spacing(_pango_units(max(0.0, extra)))
        self._column_pitch = max(natural, LINE_SPACING * self._size)

    @property
    def column_pitch(self):
        """Distance from one column to the next."""
        return self._column_pitch

    @property
    def size(self):
        return self._size

    def set_size(self, size):
        self._size = max(8.0, min(96.0, float(size)))
        self._apply_font()

    @property
    def text(self):
        return self._layout.get_text()

    def set_text(self, text):
        # A trailing newline would otherwise be invisible; Pango keeps the empty
        # last line only if we ask for it explicitly when measuring.
        self._layout.set_text(text, -1)

    def set_column_length(self, pixels):
        """How long a column may get before the text wraps to the next one."""
        self._column_length = max(0, int(pixels))
        self._layout.set_width(_pango_units(self._column_length) if pixels > 0 else -1)

    # ---- metrics ---------------------------------------------------------

    @property
    def layout(self):
        return self._layout

    @property
    def em(self):
        return self._size

    @property
    def padding_inline(self):
        return PAD_INLINE * self._size

    @property
    def padding_block(self):
        return PAD_BLOCK * self._size

    def size_px(self):
        """(along the column, across the columns) in pixels."""
        w, h = self._layout.get_size()
        return w / SCALE, h / SCALE

    def line_count(self):
        return self._layout.get_line_count()

    def line_boxes(self):
        """Logical rectangle of every line, in layout coordinates."""
        boxes = []
        it = self._layout.get_iter()
        while True:
            _ink, log = it.get_line_extents()
            boxes.append((log.x / SCALE, log.y / SCALE,
                          log.width / SCALE, log.height / SCALE))
            if not it.next_line():
                break
        return boxes

    def logical_line_starts(self):
        """Byte index at which each logical line (paragraph) begins."""
        starts = [0]
        index = 0
        for ch in self.text:
            index += len(ch.encode("utf-8"))
            if ch == "\n":
                starts.append(index)
        return starts

    def visual_line_of(self, index):
        """Index of the visual line (column) holding a byte index."""
        line, _x = self._layout.index_to_line_x(index, False)
        return line

    def caret_rect(self, index):
        """Caret rectangle for a byte index, in layout coordinates.

        This is the number the CSS build could never get hold of: with it the
        caret is drawn exactly where the text actually is.
        """
        strong, _weak = self._layout.get_cursor_pos(index)
        return (strong.x / SCALE, strong.y / SCALE,
                strong.width / SCALE, strong.height / SCALE)

    def selection_rects(self, start_byte, end_byte):
        """Rectangles covering a byte range, one per visual line it spans."""
        if start_byte == end_byte:
            return []
        low, high = sorted((start_byte, end_byte))
        rects = []
        it = self._layout.get_iter()
        while True:
            line = it.get_line_readonly()
            _ink, log = it.get_line_extents()
            line_start = line.start_index
            line_end = line_start + line.length
            if line_end > low and line_start < high:
                # get_x_ranges() is not usable through the bindings (it comes
                # back as a bare count), so take the two edge positions instead.
                # Japanese runs one way, so the span between them is the range.
                x0 = self._x_in_line(line, max(low, line_start), log)
                x1 = self._x_in_line(line, min(high, line_end), log)
                rects.append((min(x0, x1), log.y / SCALE,
                              abs(x1 - x0), log.height / SCALE))
            if not it.next_line():
                break
        return rects

    @staticmethod
    def _x_in_line(line, index, log):
        """Position of a byte index along its own line, in pixels."""
        if index >= line.start_index + line.length:
            return (log.x + log.width) / SCALE
        return line.index_to_x(index, False) / SCALE

    def index_at(self, x, y):
        """Nearest position to a point, as (byte index, trailing characters).

        Pango reports 'trailing' as a count of *characters* past the byte index,
        so the two must not simply be added together - the caller converts the
        byte index first and then steps on by that many characters.
        """
        _inside, index, trailing = self._layout.xy_to_index(
            _pango_units(x), _pango_units(y))
        return index, trailing
