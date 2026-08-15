(function () {
  var editor = document.getElementById("editor");
  editor.setAttribute("data-placeholder", "ここに書き始めてください…");

  function post(msg) {
    if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.app) {
      window.webkit.messageHandlers.app.postMessage(JSON.stringify(msg));
    }
  }

  function reportCount() {
    var text = editor.innerText.replace(/\n$/, "");
    post({ type: "count", count: text.length });
  }

  editor.addEventListener("input", function () {
    post({ type: "modified" });
    reportCount();
  });

  window.setContent = function (text) {
    editor.innerText = text;
    reportCount();
    editor.focus();
  };

  window.requestSave = function () {
    var text = editor.innerText.replace(/\n$/, "");
    post({ type: "content", text: text });
  };

  window.setFontSize = function (px) {
    editor.style.fontSize = px + "px";
  };

  window.getFontSize = function () {
    return parseInt(window.getComputedStyle(editor).fontSize, 10);
  };

  editor.focus();
  reportCount();
})();
