"use strict";

const elements = {
  list: document.querySelector("#article-list"),
  count: document.querySelector("#article-count"),
  search: document.querySelector("#search"),
  noResults: document.querySelector("#no-results"),
  detail: document.querySelector("#article-detail"),
  loading: document.querySelector("#loading"),
  content: document.querySelector("#article-content"),
  error: document.querySelector("#error-state"),
  title: document.querySelector("#article-title"),
  summary: document.querySelector("#article-summary"),
  fullArticle: document.querySelector("#full-article"),
  position: document.querySelector("#position-label"),
  source: document.querySelector("#source-link"),
  copy: document.querySelector("#copy-button"),
  previous: document.querySelector("#previous-button"),
  next: document.querySelector("#next-button"),
};

let articles = [];
let selectedNumber = null;

function numberOf(article) {
  return Number.parseInt(article.article.match(/\d+/)?.[0], 10);
}

function filteredArticles() {
  const query = elements.search.value.trim().toLowerCase();
  if (!query) return articles;
  return articles.filter((article) =>
    `${article.article} ${article.summary}`.toLowerCase().includes(query)
  );
}

function renderList() {
  const matches = filteredArticles();
  elements.list.replaceChildren();
  elements.noResults.hidden = matches.length > 0;

  for (const article of matches) {
    const number = numberOf(article);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "article-item";
    button.dataset.article = String(number);
    button.setAttribute("aria-current", String(number === selectedNumber));
    button.setAttribute("aria-label", `${article.article}: ${article.summary}`);

    const label = document.createElement("span");
    label.className = "item-number";
    label.textContent = article.article;
    const summary = document.createElement("span");
    summary.className = "item-summary";
    summary.textContent = article.summary;

    button.append(label, summary);
    button.addEventListener("click", () => selectArticle(number));
    elements.list.append(button);
  }
}

function selectArticle(number, { scroll = true } = {}) {
  const article = articles.find((item) => numberOf(item) === number);
  if (!article) return;

  selectedNumber = number;
  const index = articles.indexOf(article);
  elements.title.textContent = `Article ${number}`;
  elements.summary.textContent = article.summary;
  elements.fullArticle.textContent = article.full_article;
  elements.position.textContent = `${String(index + 1).padStart(2, "0")} / ${String(articles.length).padStart(2, "0")}`;
  elements.source.href = `https://gdpr-info.eu/art-${number}-gdpr/`;
  elements.previous.disabled = index === 0;
  elements.next.disabled = index === articles.length - 1;
  document.title = `Article ${number} — GDPR Explorer`;

  for (const button of elements.list.querySelectorAll(".article-item")) {
    button.setAttribute("aria-current", String(Number(button.dataset.article) === number));
  }

  history.replaceState(null, "", `#article-${number}`);
  if (scroll) elements.detail.scrollTo({ top: 0, behavior: "smooth" });
}

async function copyArticle() {
  const article = articles.find((item) => numberOf(item) === selectedNumber);
  if (!article) return;
  const label = elements.copy.querySelector("span");
  try {
    await navigator.clipboard.writeText(`${article.article}\n\n${article.full_article}`);
    label.textContent = "Copied";
  } catch {
    label.textContent = "Copy unavailable";
  }
  window.setTimeout(() => { label.textContent = "Copy article"; }, 1600);
}

async function loadArticles() {
  try {
    const response = await fetch("gdpr.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    if (!Array.isArray(payload.GDPR) || payload.GDPR.length === 0) {
      throw new Error("No articles in GDPR index");
    }

    articles = payload.GDPR
      .filter((article) => article.article && article.summary && article.full_article)
      .sort((a, b) => numberOf(a) - numberOf(b));
    if (!articles.length) throw new Error("No complete articles in GDPR index");

    elements.count.textContent = `${articles.length} ${articles.length === 1 ? "article" : "articles"} indexed`;
    const hashNumber = Number.parseInt(location.hash.match(/\d+/)?.[0], 10);
    const initial = articles.some((article) => numberOf(article) === hashNumber)
      ? hashNumber
      : numberOf(articles[0]);

    renderList();
    selectArticle(initial, { scroll: false });
    elements.loading.hidden = true;
    elements.content.hidden = false;
    elements.detail.setAttribute("aria-busy", "false");
  } catch (error) {
    console.error("Could not load GDPR articles:", error);
    elements.loading.hidden = true;
    elements.content.hidden = true;
    elements.error.hidden = false;
    elements.count.textContent = "Index unavailable";
    elements.detail.setAttribute("aria-busy", "false");
  }
}

elements.search.addEventListener("input", renderList);
elements.copy.addEventListener("click", copyArticle);
elements.previous.addEventListener("click", () => {
  const index = articles.findIndex((article) => numberOf(article) === selectedNumber);
  if (index > 0) selectArticle(numberOf(articles[index - 1]));
});
elements.next.addEventListener("click", () => {
  const index = articles.findIndex((article) => numberOf(article) === selectedNumber);
  if (index >= 0 && index < articles.length - 1) selectArticle(numberOf(articles[index + 1]));
});

document.addEventListener("keydown", (event) => {
  if (event.key === "/" && document.activeElement !== elements.search) {
    event.preventDefault();
    elements.search.focus();
  }
  if (event.key === "Escape" && document.activeElement === elements.search) {
    elements.search.value = "";
    elements.search.blur();
    renderList();
  }
});

window.addEventListener("hashchange", () => {
  const number = Number.parseInt(location.hash.match(/\d+/)?.[0], 10);
  if (number && number !== selectedNumber) selectArticle(number);
});

loadArticles();
