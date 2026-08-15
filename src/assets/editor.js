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

  function report() {
    var text = currentText();
    post({ type: "changed", text: text, count: text.length });
  }

  editor.addEventListener("input", report);

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
      var range = document.createRange();
      range.selectNodeContents(editor);
      range.collapse(true);
      var sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      document.execCommand("insertParagraph");
      // Leave the caret on the new second line.
      if (editor.childNodes.length > 1) {
        var last = document.createRange();
        last.selectNodeContents(editor.childNodes[1]);
        last.collapse(true);
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
    // Put the caret at the very start; focus() alone lands it between blocks.
    var start = document.createRange();
    start.selectNodeContents(editor);
    start.collapse(true);
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(start);
  };

  window.setFontSize = function (px) {
    editor.style.fontSize = px + "px";
  };

  window.getFontSize = function () {
    return parseInt(window.getComputedStyle(editor).fontSize, 10);
  };

  editor.focus();
})();
