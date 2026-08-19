/* Client-side search over the generated index. No dependencies. */
(function () {
  var box = document.getElementById("q");
  var panel = document.getElementById("results");
  if (!box || !panel) return;

  var index = null, hits = [], sel = -1;

  function load() {
    if (index) return Promise.resolve(index);
    return fetch("search-index.json")
      .then(function (r) { return r.json(); })
      .then(function (data) { index = data; return index; })
      .catch(function () { index = []; return index; });
  }

  function score(entry, needle) {
    var title = entry.t.toLowerCase();
    if (title === needle || title === "/" + needle) return 0;
    if (title.indexOf(needle) === 0 || title.indexOf("/" + needle) === 0) return 1;
    if (title.indexOf(needle) !== -1) return 2;
    if ((entry.d || "").toLowerCase().indexOf(needle) !== -1) return 3;
    return -1;
  }

  function render() {
    if (!hits.length) {
      panel.innerHTML = '<div class="empty">Nothing matches.</div>';
      panel.hidden = false;
      return;
    }
    panel.innerHTML = hits.map(function (h, i) {
      return '<a href="' + h.p + "#" + h.a + '" class="' + (i === sel ? "sel" : "") + '">' +
             '<span class="r-k">' + h.k + "</span>" +
             '<span class="r-t">' + h.t + "</span>" +
             (h.d ? '<span class="r-d">' + h.d + "</span>" : "") + "</a>";
    }).join("");
    panel.hidden = false;
  }

  function search() {
    var needle = box.value.trim().toLowerCase().replace(/^\//, "");
    if (needle.length < 2) { panel.hidden = true; hits = []; return; }
    load().then(function (data) {
      var scored = [];
      for (var i = 0; i < data.length; i++) {
        var s = score(data[i], needle);
        if (s >= 0) scored.push([s, i, data[i]]);
      }
      scored.sort(function (a, b) { return a[0] - b[0] || a[1] - b[1]; });
      hits = scored.slice(0, 25).map(function (x) { return x[2]; });
      sel = -1;
      render();
    });
  }

  box.addEventListener("input", search);
  box.addEventListener("focus", function () { if (hits.length) panel.hidden = false; });

  box.addEventListener("keydown", function (e) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      if (!hits.length) return;
      e.preventDefault();
      sel = (sel + (e.key === "ArrowDown" ? 1 : hits.length - 1)) % hits.length;
      render();
      var node = panel.children[sel];
      if (node && node.scrollIntoView) node.scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter") {
      var target = hits[sel < 0 ? 0 : sel];
      if (target) { e.preventDefault(); window.location.href = target.p + "#" + target.a; }
    } else if (e.key === "Escape") {
      panel.hidden = true; box.blur();
    }
  });

  document.addEventListener("click", function (e) {
    if (!panel.contains(e.target) && e.target !== box) panel.hidden = true;
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "/" && document.activeElement !== box &&
        !/^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName)) {
      e.preventDefault(); box.focus(); box.select();
    }
  });

  load();   // warm the index so the first keystroke is instant
})();
