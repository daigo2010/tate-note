(function () {
  var editor = document.getElementById("editor");
  editor.setAttribute("data-placeholder", "ここから書き始めてください");

  function post(msg) {
    if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.app) {
      window.webkit.messageHandlers.app.postMessage(JSON.stringify(msg));
    }
  }

  function currentText() {
    return editor.innerText.replace(/\n$/, "");
  }

  function caretToStart() {
    var range = document.createRange();
    range.selectNodeContents(editor);
    range.collapse(true);
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  }

  // ---- display options (driven from the GTK settings menu) -----------------

  var options = { lineNumbers: false, showWhitespace: false };

  // Caret position as a character index over the editor's text nodes. Range
  // .toString() skips block boundaries, so the same "space" is used to restore.
  function caretOffset() {
    var sel = window.getSelection();
    if (!sel.rangeCount) return -1;
    var r = sel.getRangeAt(0);
    if (!editor.contains(r.startContainer)) return -1;
    var pre = document.createRange();
    pre.selectNodeContents(editor);
    pre.setEnd(r.startContainer, r.startOffset);
    return pre.toString().length;
  }

  function applyCaretOffset(index) {
    var walker = document.createTreeWalker(editor, NodeFilter.SHOW_TEXT, null);
    var seen = 0, node, last = null;
    while ((node = walker.nextNode())) {
      if (index <= seen + node.data.length) {
        var r = document.createRange();
        r.setStart(node, index - seen);
        r.collapse(true);
        var sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(r);
        return;
      }
      seen += node.data.length;
      last = node;
    }
    if (last) {
      var end = document.createRange();
      end.setStart(last, last.data.length);
      end.collapse(true);
      var s2 = window.getSelection();
      s2.removeAllRanges();
      s2.addRange(end);
    }
  }

  // Run a DOM rewrite without moving the caret. A live selection is left alone
  // (decorating must never collapse it); with no caret at all - e.g. the
  // settings popover holds the focus - the rewrite still runs, there is just
  // nothing to restore.
  function withCaret(mutate) {
    var sel = window.getSelection();
    if (sel.rangeCount && !sel.getRangeAt(0).collapsed) return false;
    var offset = caretOffset();
    if (!mutate()) return false;
    if (offset >= 0) applyCaretOffset(offset);
    return true;
  }

  // Line numbers and the ⏎ marker are ::before/::after on the line boxes, so
  // every line has to actually be a <div>. Typing leaves the first line as a
  // bare text node; wrap it. Generated content never reaches innerText, so the
  // saved file is unaffected.
  function ensureLineDivs() {
    if (!editor.firstChild || editor.firstChild.nodeName === "DIV") return false;
    var line = document.createElement("div");
    while (editor.firstChild && editor.firstChild.nodeName !== "DIV") {
      line.appendChild(editor.firstChild);
    }
    editor.insertBefore(line, editor.firstChild);
    return true;
  }

  var WS_CLASS = { " ": "tate-sp", "\t": "tate-tab", "　": "tate-wsp" };
  var MARKER_SELECTOR = "span.tate-sp, span.tate-tab, span.tate-wsp";

  function lineNeedsMarkers(line) {
    var wanted = 0, text = line.textContent;
    for (var i = 0; i < text.length; i++) if (WS_CLASS[text[i]]) wanted++;
    if (wanted !== line.querySelectorAll(MARKER_SELECTOR).length) return true;
    for (var n = line.firstChild; n; n = n.nextSibling) {
      if (n.nodeType === 3) {
        for (var j = 0; j < n.data.length; j++) if (WS_CLASS[n.data[j]]) return true;
      }
    }
    return false;
  }

  // Markers carry background/outline only - never anything that changes metrics,
  // so wrapping cannot reflow the text.
  function addMarkers(line) {
    var text = line.textContent;
    if (!text) return false;               // empty line: just a <br>, leave it
    var frag = document.createDocumentFragment();
    var buf = "";
    function flush() {
      if (buf) { frag.appendChild(document.createTextNode(buf)); buf = ""; }
    }
    for (var i = 0; i < text.length; i++) {
      var cls = WS_CLASS[text[i]];
      if (cls) {
        flush();
        var span = document.createElement("span");
        span.className = cls;
        span.textContent = text[i];
        frag.appendChild(span);
      } else {
        buf += text[i];
      }
    }
    flush();
    line.textContent = "";
    line.appendChild(frag);
    return true;
  }

  function stripMarkers(line) {
    if (!line.querySelector || !line.querySelector(MARKER_SELECTOR)) return false;
    line.textContent = line.textContent;
    return true;
  }

  function refreshDecorations() {
    if (!options.lineNumbers && !options.showWhitespace) {
      if (editor.querySelector(MARKER_SELECTOR)) {
        withCaret(function () {
          var changed = false;
          for (var i = 0; i < editor.children.length; i++) {
            changed = stripMarkers(editor.children[i]) || changed;
          }
          return changed;
        });
      }
      return;
    }
    withCaret(function () {
      var changed = ensureLineDivs();
      for (var i = 0; i < editor.children.length; i++) {
        var line = editor.children[i];
        if (line.nodeName !== "DIV") continue;
        if (options.showWhitespace) {
          if (lineNeedsMarkers(line)) changed = addMarkers(line) || changed;
        } else {
          changed = stripMarkers(line) || changed;
        }
      }
      return changed;
    });
  }

  window.setOptions = function (opts) {
    options.lineNumbers = !!opts.lineNumbers;
    options.showWhitespace = !!opts.showWhitespace;
    editor.classList.toggle("tate-linenum", options.lineNumbers);
    editor.classList.toggle("tate-ws", options.showWhitespace);
    refreshDecorations();
  };

  // The IME must never see the DOM change mid-composition.
  var composing = false;
  editor.addEventListener("compositionstart", function () { composing = true; });
  editor.addEventListener("compositionend", function () { composing = false; report(); });

  function report() {
    var text = currentText();
    if (text === "" && !composing && editor.childNodes.length) {
      // Deleting the last character leaves a stray <br> behind. The editor is
      // then no longer :empty (so the placeholder stays hidden) and WebKit
      // paints the caret above the padding box. Reset to a genuinely empty
      // editor, which is also the state the Enter handler below expects.
      editor.innerHTML = "";
      caretToStart();
    } else if (!composing) {
      refreshDecorations();
      text = currentText();
    }
    post({ type: "changed", text: text, count: text.length });
  }

  editor.addEventListener("input", report);

  // Arrow keys must follow the *visual* directions, not the logical ones. In
  // vertical-rl WebKit's defaults are rotated: Down/Up jump between columns and
  // Left/Right walk along one. Measured mapping back to what the eye expects:
  //   forward/character  = visually down      backward/character = visually up
  //   forward/line       = visually left      backward/line      = visually right
  var ARROWS = {
    ArrowDown:  ["forward", "character"],
    ArrowUp:    ["backward", "character"],
    ArrowLeft:  ["forward", "line"],
    ArrowRight: ["backward", "line"]
  };
  editor.addEventListener("keydown", function (e) {
    var move = ARROWS[e.key];
    if (!move || e.isComposing || e.ctrlKey || e.altKey || e.metaKey) return;
    var sel = window.getSelection();
    if (!sel.modify) return;
    e.preventDefault();
    sel.modify(e.shiftKey ? "extend" : "move", move[0], move[1]);
  });

  // Tab would otherwise move the focus out of the editor instead of indenting.
  // A literal tab is safe here - unlike "\n" it does not disturb the caret.
  editor.addEventListener("keydown", function (e) {
    if (e.key === "Tab" && !e.isComposing && !e.ctrlKey && !e.altKey && !e.metaKey) {
      e.preventDefault();
      document.execCommand("insertText", false, "\t");
    }
  });

  // Do NOT override Enter in general. Forcing a plain line break (or any literal
  // "\n" in this white-space:pre-wrap box) makes WebKit paint the caret one
  // line-height further down on every empty line in vertical writing mode, so
  // the cursor walks diagonally away from the text. WebKit's native <div>-per-
  // line breaking positions the caret correctly; currentText() normalises it.
  // The one exception: with no child nodes at all there is no line to split, so
  // the first Enter in an untouched document would be a no-op.
  editor.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.isComposing && editor.childNodes.length === 0) {
      e.preventDefault();
      editor.focus();
      caretToStart();
      document.execCommand("insertParagraph");
      // Leave the caret on the new second line.
      if (editor.childNodes.length > 1) {
        var last = document.createRange();
        last.selectNodeContents(editor.childNodes[1]);
        last.collapse(true);
        var sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(last);
      }
      report();
    }
  });

  // Keep pasted text plain so the buffer stays a faithful .txt mirror.
  editor.addEventListener("paste", function (e) {
    e.preventDefault();
    var text = (e.clipboardData || window.clipboardData).getData("text/plain");
    // Insert line by line via insertParagraph so pasted breaks use WebKit's own
    // line model rather than literal "\n" characters.
    var lines = text.split(/\r\n|\r|\n/);
    for (var i = 0; i < lines.length; i++) {
      if (i) document.execCommand("insertParagraph");
      if (lines[i]) document.execCommand("insertText", false, lines[i]);
    }
  });

  // In vertical-rl the text flows leftwards, so the wheel's vertical delta has
  // to drive the horizontal (block) axis. scrollLeft runs from -(overflow) to 0.
  editor.addEventListener("wheel", function (e) {
    if (e.ctrlKey) return;
    var delta = e.deltaY || e.deltaX;
    if (!delta) return;
    if (e.deltaMode === 1) delta *= 16;      // lines
    else if (e.deltaMode === 2) delta *= editor.clientWidth;
    editor.scrollLeft -= delta;
    e.preventDefault();
  }, { passive: false });

  window.setContent = function (text) {
    // Build one <div> per line — the same structure WebKit produces while
    // typing — so a loaded document behaves identically to a typed one, caret
    // included. "editor.innerText = text" would instead emit bare <br>s and
    // silently drop trailing blank lines.
    editor.textContent = "";
    if (text !== "") {
      var lines = text.split("\n");
      for (var i = 0; i < lines.length; i++) {
        var line = document.createElement("div");
        line.appendChild(lines[i] ? document.createTextNode(lines[i])
                                  : document.createElement("br"));
        editor.appendChild(line);
      }
    }
    editor.scrollLeft = 0;  // back to the first column, on the right
    editor.focus();
    caretToStart();  // focus() alone lands the caret between blocks
    refreshDecorations();
  };

  window.setFontSize = function (px) {
    editor.style.fontSize = px + "px";
  };

  window.getFontSize = function () {
    return parseInt(window.getComputedStyle(editor).fontSize, 10);
  };

  editor.focus();
})();
