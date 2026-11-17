/* DeepSeek Flash — GDPR Article Explorer */
(() => {
  "use strict";

  const $ = (sel) => document.querySelector(sel);

  const els = {
    list:        $("#article-list"),
    search:      $("#search"),
    resultCount: $("#result-count"),
    countBadge:  $("#count-badge"),
    modelBadge:  $("#model-badge"),
    empty:       $("#reader-empty"),
    reader:      $("#reader"),
    label:       $("#doc-label"),
    title:       $("#doc-title"),
    words:       $("#doc-words"),
    body:        $("#doc-body"),
    source:      $("#source-link"),
    copy:        $("#copy-btn"),
    back:        $("#back-btn"),
    progress:    $("#progress-bar"),
    pane:        document.querySelector(".reader"),
  };

  let articles = [];
  let active = null;      // current article object
  let visible = [];       // cards currently rendered
  let cursor = -1;        // keyboard position within `visible` (-1 = none)

  /* ── helpers ─────────────────────────────────────────────────────────── */

  const esc = (s) =>
    String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const slug = (art) => "art-" + (art.article.match(/\d+/) || ["0"])[0];

  function highlight(text, query) {
    const safe = esc(text);
    if (!query) return safe;
    const tokens = query.split(/\s+/).filter((t) => t.length > 1)
      .map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    if (!tokens.length) return safe;
    const re = new RegExp(`(${tokens.join("|")})`, "gi");
    return safe.replace(re, "<mark>$1</mark>");
  }

  /* ── list rendering ──────────────────────────────────────────────────── */

  function cardFor(art, query, index) {
    const el = document.createElement("div");
    el.className = "card";
    el.id = "card-" + slug(art);
    el.setAttribute("role", "option");
    el.setAttribute("tabindex", "0");
    el.setAttribute("aria-selected", "false");
    el.dataset.index = index;
    el.innerHTML =
      `<div class="card-top">
         <span class="card-label">${esc(art.article)}</span>
         <span class="card-title">${highlight(art.title || "", query)}</span>
       </div>
       <p class="card-summary">${highlight(art.summary || "No summary available.", query)}</p>`;
    el.addEventListener("click", () => select(art, true));
    el.addEventListener("focus", () => { cursor = index; paintCursor(); });
    return el;
  }

  function renderList() {
    const q = els.search.value.trim();
    const needle = q.toLowerCase();
    visible = !needle ? articles.slice() : articles.filter((a) =>
      (a.article + " " + (a.title || "") + " " + (a.summary || "")).toLowerCase().includes(needle));

    els.list.innerHTML = "";
    if (!visible.length) {
      els.list.innerHTML = `<div class="no-results">No article matches “${esc(q)}”.</div>`;
    } else {
      visible.forEach((a, i) => els.list.appendChild(cardFor(a, q, i)));
    }

    els.resultCount.textContent = q
      ? `${visible.length} of ${articles.length}`
      : `${articles.length} total`;

    // Point the keyboard cursor at the selected article, if it survived the filter.
    const activeIndex = active ? visible.indexOf(active) : -1;
    cursor = activeIndex;
    if (active) markActive(active);
    paintCursor();
  }

  function markActive(art) {
    const card = document.getElementById("card-" + slug(art));
    els.list.querySelectorAll(".card").forEach((c) => {
      const on = c === card;
      c.classList.toggle("active", on);
      c.setAttribute("aria-selected", String(on));
    });
    if (card) card.scrollIntoView({ block: "nearest" });
  }

  function paintCursor() {
    els.list.querySelectorAll(".card").forEach((c, i) =>
      c.classList.toggle("cursor", i === cursor && !c.classList.contains("active")));
  }

  /* ── article rendering ───────────────────────────────────────────────── */

  function renderBody(text) {
    const blocks = String(text || "").split(/\n{2,}/);
    let first = true;
    return blocks.map((raw) => {
      const block = raw.trim();
      if (!block) return "";

      let m;
      if ((m = block.match(/^\(([a-z])\)\s*([\s\S]*)$/i))) {
        return `<p class="point"><span class="marker">(${esc(m[1])})</span>${esc(m[2])}</p>`;
      }
      if ((m = block.match(/^([•\-*])\s+([\s\S]*)$/))) {
        return `<p class="point"><span class="marker">•</span>${esc(m[2])}</p>`;
      }
      if ((m = block.match(/^(\d+)\.\s*([\s\S]*)$/))) {
        const cls = first ? ' class="lede"' : "";
        first = false;
        return `<p${cls}><span class="num">${esc(m[1])}.</span>${esc(m[2])}</p>`;
      }
      const cls = first ? ' class="lede"' : "";
      first = false;
      return `<p${cls}>${esc(block)}</p>`;
    }).join("");
  }

  function select(art, updateHash = true) {
    active = art;

    els.empty.hidden = true;
    els.reader.hidden = false;
    els.label.textContent = art.article;
    els.title.textContent = art.title || "—";
    els.body.innerHTML = renderBody(art.full_article);

    const n = (art.full_article || "").trim().split(/\s+/).filter(Boolean).length;
    els.words.textContent = `${n.toLocaleString()} words · ~${Math.max(1, Math.round(n / 220))} min read`;

    const num = (art.article.match(/\d+/) || [""])[0];
    els.source.href = num ? `https://gdpr-info.eu/art-${num}-gdpr/` : "https://gdpr-info.eu/";

    const i = visible.indexOf(art);
    if (i >= 0) cursor = i;
    markActive(art);
    paintCursor();

    els.pane.scrollTop = 0;
    setProgress(0);
    document.body.classList.add("show-reader");

    if (updateHash) history.replaceState(null, "", "#" + slug(art));
    els.copy.classList.remove("copied");
    els.copy.querySelector("span").textContent = "Copy text";
  }

  function setProgress(x) { els.progress.style.transform = `scaleX(${x})`; }

  /* ── events ──────────────────────────────────────────────────────────── */

  els.search.addEventListener("input", renderList);

  els.search.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { els.search.value = ""; renderList(); els.search.blur(); }
    if (e.key === "ArrowDown" && visible.length) { e.preventDefault(); select(visible[0]); els.search.blur(); }
  });

  document.addEventListener("keydown", (e) => {
    const typing = ["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName);
    if (typing && e.key !== "Escape") return;

    if (e.key === "/" && !typing) {
      e.preventDefault();
      els.search.focus();
      els.search.select();
      return;
    }
    if (!visible.length) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      cursor = Math.min(cursor + 1, visible.length - 1);
      select(visible[cursor]);
      document.getElementById("card-" + slug(visible[cursor]))?.focus({ preventScroll: true });
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      cursor = Math.max(cursor - 1, 0);
      select(visible[cursor]);
      document.getElementById("card-" + slug(visible[cursor]))?.focus({ preventScroll: true });
    } else if (e.key === "Enter" && !typing && visible[cursor]) {
      select(visible[cursor]);
    } else if (e.key === "Escape") {
      document.body.classList.remove("show-reader");
    }
  });

  els.copy.addEventListener("click", async () => {
    if (!active) return;
    const text = `${active.article} GDPR — ${active.title}\n\n${active.full_article}`;
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    els.copy.classList.add("copied");
    els.copy.querySelector("span").textContent = "Copied ✓";
    setTimeout(() => {
      els.copy.classList.remove("copied");
      els.copy.querySelector("span").textContent = "Copy text";
    }, 1800);
  });

  els.back.addEventListener("click", () => document.body.classList.remove("show-reader"));

  window.addEventListener("hashchange", () => {
    const wanted = location.hash.replace(/^#/, "");
    const art = articles.find((a) => slug(a) === wanted);
    if (art && art !== active) select(art, false);
    if (!wanted) document.body.classList.remove("show-reader");
  });

  els.pane.addEventListener("scroll", () => {
    const max = els.pane.scrollHeight - els.pane.clientHeight;
    setProgress(max > 0 ? els.pane.scrollTop / max : 0);
  }, { passive: true });

  /* ── boot ────────────────────────────────────────────────────────────── */

  async function boot() {
    try {
      const res = await fetch("/api/articles", { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      articles = data.articles || [];

      els.countBadge.textContent = `${articles.length} article${articles.length === 1 ? "" : "s"}`;
      if (data.model) els.modelBadge.textContent = data.model.replace(/\s*\(.*\)/, "") + " · local";

      renderList();

      const wanted = location.hash.replace(/^#/, "");
      const fromHash = articles.find((a) => slug(a) === wanted);
      if (fromHash) select(fromHash, false);
    } catch (err) {
      els.list.innerHTML =
        `<div class="no-results">Could not load articles.<br><code>${esc(err.message)}</code><br><br>
         Run <code>python3 scrape_gdpr.py</code> first.</div>`;
      els.countBadge.textContent = "offline";
    }
  }

  boot();
})();
