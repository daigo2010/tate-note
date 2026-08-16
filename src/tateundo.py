"""Undo and redo history for the vertical text view.

Every change to a document is one contiguous replacement: at `start`, `removed`
became `inserted`. That is enough to invert, and enough to group - a run of
typing or a run of backspacing merges into a single step, so undo moves in the
units a writer thinks in rather than one character at a time.
"""

MAX_RUN = 64            # characters before a run becomes a step of its own


class Edit:
    """One replacement, with the caret either side of it."""

    __slots__ = ("start", "removed", "inserted", "before", "after")

    def __init__(self, start, removed, inserted, before, after):
        self.start = start
        self.removed = removed
        self.inserted = inserted
        self.before = before            # (caret, anchor) as the edit was made
        self.after = after              # (caret, anchor) once it was applied

    @property
    def end(self):
        """Where the inserted text finishes, in the edited document."""
        return self.start + len(self.inserted)


class UndoStack:
    def __init__(self):
        self.reset()

    def reset(self):
        self._done = []
        self._undone = []
        self._sealed = True             # nothing may merge into the top entry

    @property
    def can_undo(self):
        return bool(self._done)

    @property
    def can_redo(self):
        return bool(self._undone)

    def barrier(self):
        """End the current run so the next edit starts a fresh step.

        Moving the caret is the usual reason: text typed somewhere else is a
        separate thought, and undoing it should not swallow what came before.
        """
        self._sealed = True

    def record(self, edit):
        # A fresh edit is a new branch of history; what was undone is gone.
        self._undone = []
        if not self._sealed and self._done and self._merge(self._done[-1], edit):
            return
        self._done.append(edit)
        self._sealed = False

    def _merge(self, top, new):
        """Fold `new` into `top` when the two are one continuous run."""
        if not new.removed and not top.removed:
            # Typing on from where the last insertion left off. A newline ends
            # the run: a line is a natural thing to want back whole.
            if (new.start == top.end
                    and "\n" not in top.inserted and "\n" not in new.inserted
                    and len(top.inserted) + len(new.inserted) <= MAX_RUN):
                top.inserted += new.inserted
                top.after = new.after
                return True
            return False
        if not new.inserted and not top.inserted:
            if len(top.removed) + len(new.removed) > MAX_RUN:
                return False
            # Backspacing on: each step eats the character before the last.
            if new.start + len(new.removed) == top.start:
                top.removed = new.removed + top.removed
                top.start = new.start
                top.after = new.after
                return True
            # Delete, which keeps eating at the same spot.
            if new.start == top.start:
                top.removed += new.removed
                top.after = new.after
                return True
        return False

    def undo(self):
        """The edit to reverse, or None."""
        if not self._done:
            return None
        edit = self._done.pop()
        self._undone.append(edit)
        self._sealed = True
        return edit

    def redo(self):
        """The edit to re-apply, or None."""
        if not self._undone:
            return None
        edit = self._undone.pop()
        self._done.append(edit)
        self._sealed = True
        return edit
