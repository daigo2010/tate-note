(function () {
  var editor = document.getElementById("editor");
  editor.setAttribute("data-placeholder", "ここに書き始めてください…");

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
  };

  window.setFontSize = function (px) {
    editor.style.fontSize = px + "px";
  };

  window.getFontSize = function () {
    return parseInt(window.getComputedStyle(editor).fontSize, 10);
  };

  editor.focus();
})();
