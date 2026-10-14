// Staff session timeout warning (WCAG 2.2.1 Timing Adjustable).
// Warns 5 minutes before the idle limit and lets the person extend with one action.
(function () {
  "use strict";
  var IDLE_LIMIT = 60 * 60 * 1000;
  var WARN_AT = IDLE_LIMIT - 5 * 60 * 1000;
  var box = document.getElementById("session-warning");
  var stay = document.getElementById("stay-signed-in");
  if (!box || !stay) { return; }
  var timer;
  function arm() {
    clearTimeout(timer);
    timer = setTimeout(function () { box.hidden = false; stay.focus(); }, WARN_AT);
  }
  stay.addEventListener("click", function () {
    var token = document.querySelector("input[name=_csrf]");
    fetch((document.documentElement.getAttribute("data-base") || "") + "/staff/ping", { method: "POST", credentials: "same-origin",
      headers: { "x-csrf-token": token ? token.value : "" } }).finally(function () {
      box.hidden = true; arm();
    });
  });
  arm();
})();

// Redaction tool: drag on a page image to fill the box fields.
(function () {
  "use strict";
  var img = document.getElementById("redact-image");
  if (!img) { return; }
  var fields = ["x", "y", "w", "h"].map(function (k) { return document.getElementById("mark-" + k); });
  var start = null;
  function pos(e) {
    var r = img.getBoundingClientRect();
    return { x: Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)),
             y: Math.max(0, Math.min(1, (e.clientY - r.top) / r.height)) };
  }
  img.addEventListener("pointerdown", function (e) { start = pos(e); e.preventDefault(); });
  window.addEventListener("pointerup", function (e) {
    if (!start) { return; }
    var end = pos(e);
    var x = Math.min(start.x, end.x), y = Math.min(start.y, end.y);
    var w = Math.abs(end.x - start.x), h = Math.abs(end.y - start.y);
    [x, y, w, h].forEach(function (v, i) { fields[i].value = (v * 100).toFixed(1); });
    start = null;
    document.getElementById("mark-reason").focus();
  });
})();
