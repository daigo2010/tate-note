"""The folder pane: a directory tree for working through a set of documents.

Built on GTK4's tree list model rather than the deprecated GtkTreeView. Hidden
entries are left out, which also keeps the dot-prefixed memo files that sit
beside each document from cluttering the tree.
"""

import os

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import GLib, Gio, GObject, Gtk

TREE_WIDTH = 220


class FileNode(GObject.Object):
    """One entry in the folder tree."""

    __gtype_name__ = "TateFileNode"

    def __init__(self, path):
        super().__init__()
        self.path = path
        self.name = os.path.basename(path) or path
        self.is_dir = os.path.isdir(path)


def _sort_key(node):
    # Collating as a *filename* keeps embedded numbers in order, so a chapter
    # set reads 1, 2, 10 rather than 1, 10, 2.
    return (not node.is_dir, GLib.utf8_collate_key_for_filename(node.name, -1))


def _entries(directory):
    """Directories first, then files, each in name order; hidden ones skipped."""
    try:
        names = os.listdir(directory)
    except OSError:
        return []
    nodes = [FileNode(os.path.join(directory, n))
             for n in names if not n.startswith(".")]
    nodes.sort(key=_sort_key)
    return nodes


class FolderTree(Gtk.Box):
    """Shows a folder; asks to open the file that was activated."""

    __gtype_name__ = "TateFolderTree"

    __gsignals__ = {
        "file-activated": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "folder-requested": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_size_request(TREE_WIDTH, -1)
        self.add_css_class("tate-memo-side")
        self.root = None

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header.add_css_class("tate-memo-heading")
        self.heading = Gtk.Label(label="フォルダ", xalign=0.0, hexpand=True)
        self.heading.set_ellipsize(3)                    # PANGO_ELLIPSIZE_END
        for edge in ("top", "bottom", "start", "end"):
            getattr(header, "set_margin_" + edge)(4)
        header.append(self.heading)
        open_btn = Gtk.Button(icon_name="folder-open-symbolic")
        open_btn.set_tooltip_text("フォルダを開く")
        open_btn.set_has_frame(False)
        open_btn.connect("clicked", lambda _b: self.emit("folder-requested"))
        header.append(open_btn)
        self.append(header)
        self.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        self.selection = Gtk.SingleSelection()
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_setup)
        factory.connect("bind", self._on_bind)
        self.listview = Gtk.ListView(model=self.selection, factory=factory)
        self.listview.add_css_class("tate-memo")
        # ListView::activate is the intended hook - it fires on a double click
        # and on Enter, and hands over the row's position. A GestureClick of our
        # own does not work here: the list view's own gesture claims the press
        # first, so the second click never reaches us.
        self.listview.set_single_click_activate(False)
        self.listview.connect("activate", self._on_activate)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroller.set_child(self.listview)
        scroller.set_vexpand(True)
        self.append(scroller)

        self.placeholder = Gtk.Label(label="フォルダが開かれていません")
        self.placeholder.add_css_class("dim-label")
        self.placeholder.set_wrap(True)
        for edge in ("top", "start", "end"):
            getattr(self.placeholder, "set_margin_" + edge)(12)
        self.append(self.placeholder)

    # ---- model -----------------------------------------------------------

    def set_root(self, path):
        """Show a folder, replacing whatever was there."""
        self.root = path
        self.heading.set_text(os.path.basename(path.rstrip("/")) or path)
        self.heading.set_tooltip_text(path)
        store = Gio.ListStore.new(FileNode)
        for node in _entries(path):
            store.append(node)
        tree = Gtk.TreeListModel.new(store, False, False, self._children)
        self.selection.set_model(tree)
        self.placeholder.set_visible(False)

    def refresh(self):
        if self.root:
            self.set_root(self.root)

    def _children(self, node):
        """Child model for a directory row, or None to make the row a leaf."""
        if not node.is_dir:
            return None
        store = Gio.ListStore.new(FileNode)
        for child in _entries(node.path):
            store.append(child)
        return store

    # ---- rows ------------------------------------------------------------

    def _on_setup(self, _factory, item):
        expander = Gtk.TreeExpander()
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Image())
        row.append(Gtk.Label(xalign=0.0))
        expander.set_child(row)
        item.set_child(expander)

    def _on_bind(self, _factory, item):
        expander = item.get_child()
        listrow = item.get_item()
        node = listrow.get_item()
        expander.set_list_row(listrow)
        row = expander.get_child()
        image = row.get_first_child()
        label = image.get_next_sibling()
        image.set_from_icon_name(
            "folder-symbolic" if node.is_dir else "text-x-generic-symbolic")
        label.set_text(node.name)

    # ---- activation ------------------------------------------------------

    def _on_activate(self, _listview, position):
        """A row was double clicked, or Enter was pressed on it.

        The position is the row that was acted on, so this cannot open the
        wrong file the way reading the current selection could.
        """
        listrow = self.selection.get_item(position)
        if listrow is None:
            return
        node = listrow.get_item()
        if node.is_dir:
            listrow.set_expanded(not listrow.get_expanded())
        else:
            self.emit("file-activated", node.path)
