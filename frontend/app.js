// app.js
// Replace these with your Supabase project values
const SUPABASE_URL = "YOUR_SUPABASE_URL";
const SUPABASE_ANON_KEY = "YOUR_SUPABASE_ANON_KEY";

const supabase = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

// State
let currentCategory = "world";
let currentDate = new Date().toISOString().split("T")[0];
let availableDates = [];

// DOM elements
const eventsContainer = document.getElementById("events-container");
const currentDateEl = document.getElementById("current-date");
const prevDayBtn = document.getElementById("prev-day");
const nextDayBtn = document.getElementById("next-day");
const credibilityFilter = document.getElementById("credibility-filter");
const topOnlyToggle = document.getElementById("top-only");

// --- Data fetching ---

async function fetchAvailableDates() {
    const { data, error } = await supabase
        .from("events")
        .select("event_date")
        .eq("category", currentCategory)
        .order("event_date", { ascending: false });

    if (error) {
        console.error("Failed to fetch dates:", error);
        return;
    }

    availableDates = [...new Set(data.map((r) => r.event_date))];

    if (availableDates.length > 0 && !availableDates.includes(currentDate)) {
        currentDate = availableDates[0];
    }

    updateNavButtons();
}

async function fetchEvents() {
    eventsContainer.innerHTML = '<div class="loading">Loading...</div>';

    const credFilter = credibilityFilter.value;

    let query = supabase
        .from("events")
        .select("*")
        .eq("category", currentCategory)
        .eq("event_date", currentDate)
        .order("analyzed_at", { ascending: false });

    if (credFilter !== "all") {
        query = query.eq("credibility_score", credFilter);
    }

    const { data: events, error } = await query;

    if (error) {
        eventsContainer.innerHTML = '<div class="empty">Error loading events.</div>';
        console.error(error);
        return;
    }

    if (!events || events.length === 0) {
        eventsContainer.innerHTML = '<div class="empty">No events for this date.</div>';
        return;
    }

    for (const event of events) {
        const { data: links } = await supabase
            .from("event_articles")
            .select("article_id")
            .eq("event_id", event.id);

        if (links && links.length > 0) {
            const articleIds = links.map((l) => l.article_id);
            const { data: articles } = await supabase
                .from("articles")
                .select("*")
                .in("id", articleIds);
            event.articles = articles || [];
        } else {
            event.articles = [];
        }
    }

    renderEvents(events);
}

// --- Rendering ---

function renderEvents(events) {
    eventsContainer.innerHTML = "";

    for (const event of events) {
        const card = document.createElement("div");
        card.className = "event-card";
        card.innerHTML = renderEventCard(event);
        eventsContainer.appendChild(card);

        card.querySelector(".event-header").addEventListener("click", () => {
            const analysis = card.querySelector(".event-analysis");
            analysis.classList.toggle("open");
        });
    }
}

function renderEventCard(event) {
    const score = event.credibility_score || "unverified";
    const sourceCount = event.articles ? event.articles.length : 0;

    let analysisHtml = "";
    if (event.coverage_analysis) {
        const sources = event.coverage_analysis;
        let sourceSections = "";
        for (const [sourceName, info] of Object.entries(sources)) {
            sourceSections += `
                <div class="source-analysis">
                    <h4>${sourceName}</h4>
                    <div class="tone">Tone: ${info.tone || "n/a"}</div>
                    <div class="focus">${info.focus || ""}</div>
                </div>`;
        }
        analysisHtml = sourceSections;
    }

    let linksHtml = "";
    if (event.articles && event.articles.length > 0) {
        const links = event.articles
            .map(
                (a) =>
                    `<a href="${a.link}" target="_blank" rel="noopener">
                        <span class="source-label">[${a.source}]</span> ${a.title}
                    </a>`
            )
            .join("");
        linksHtml = `<div class="article-links"><h4>Sources</h4>${links}</div>`;
    }

    return `
        <div class="event-header">
            <span class="credibility-dot ${score}"></span>
            <span class="event-title">${event.title}</span>
        </div>
        <div class="event-meta">
            <span>${sourceCount} source${sourceCount !== 1 ? "s" : ""}</span>
            <span class="badge ${score}">${score}</span>
        </div>
        <div class="event-summary">${event.summary || ""}</div>
        <div class="event-analysis">
            ${analysisHtml}
            ${event.credibility_reasoning ? `
                <div class="credibility-section">
                    <h4>Credibility Assessment</h4>
                    <p>${event.credibility_reasoning}</p>
                </div>` : ""}
            ${linksHtml}
        </div>`;
}

// --- Navigation ---

function updateNavButtons() {
    currentDateEl.textContent = formatDate(currentDate);

    const idx = availableDates.indexOf(currentDate);
    nextDayBtn.disabled = idx <= 0;
    prevDayBtn.disabled = idx >= availableDates.length - 1;
}

function formatDate(dateStr) {
    const d = new Date(dateStr + "T00:00:00");
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

prevDayBtn.addEventListener("click", () => {
    const idx = availableDates.indexOf(currentDate);
    if (idx < availableDates.length - 1) {
        currentDate = availableDates[idx + 1];
        updateNavButtons();
        fetchEvents();
    }
});

nextDayBtn.addEventListener("click", () => {
    const idx = availableDates.indexOf(currentDate);
    if (idx > 0) {
        currentDate = availableDates[idx - 1];
        updateNavButtons();
        fetchEvents();
    }
});

// --- Tabs ---

document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
        document.querySelector(".tab.active").classList.remove("active");
        tab.classList.add("active");
        currentCategory = tab.dataset.category;
        fetchAvailableDates().then(fetchEvents);
    });
});

// --- Filters ---

credibilityFilter.addEventListener("change", fetchEvents);
topOnlyToggle.addEventListener("change", fetchEvents);

// --- Init ---

fetchAvailableDates().then(fetchEvents);
