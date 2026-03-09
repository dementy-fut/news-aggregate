// app.js
const SUPABASE_URL = "https://ybcoprfkckjagjxzhfar.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InliY29wcmZrY2tqYWdqeHpoZmFyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzMwNzA4MjEsImV4cCI6MjA4ODY0NjgyMX0.4fcalkLYVD3tiWnXMLr5w6V7VHATIFr5dARYjvexW-Y";

const db = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

// Russian labels
const CRED_LABELS = {
    confirmed: "Подтверждено",
    likely: "Вероятно",
    unverified: "Не проверено",
    disputed: "Спорно",
};

// State
let currentCategory = "world";
let currentView = "daily"; // "daily" or "week"
let currentDate = new Date().toISOString().split("T")[0];
let availableDates = [];

// DOM elements
const eventsContainer = document.getElementById("events-container");
const currentDateEl = document.getElementById("current-date");
const prevDayBtn = document.getElementById("prev-day");
const nextDayBtn = document.getElementById("next-day");
const credibilityFilter = document.getElementById("credibility-filter");
const topOnlyToggle = document.getElementById("top-only");
const controlsEl = document.querySelector(".controls");

// --- Data fetching ---

async function fetchAvailableDates() {
    const { data, error } = await db
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
    eventsContainer.innerHTML = '<div class="loading">Загрузка...</div>';

    const credFilter = credibilityFilter.value;

    let query = db
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
        eventsContainer.innerHTML = '<div class="empty">Ошибка загрузки.</div>';
        console.error(error);
        return;
    }

    if (!events || events.length === 0) {
        eventsContainer.innerHTML = '<div class="empty">Нет событий за эту дату.</div>';
        return;
    }

    await loadArticlesForEvents(events);
    renderEvents(events);
}

async function fetchWeekEvents() {
    eventsContainer.innerHTML = '<div class="loading">Загрузка недели...</div>';

    const today = new Date();
    const weekAgo = new Date(today);
    weekAgo.setDate(today.getDate() - 7);
    const fromDate = weekAgo.toISOString().split("T")[0];
    const toDate = today.toISOString().split("T")[0];

    let query = db
        .from("events")
        .select("*")
        .eq("category", currentCategory)
        .gte("event_date", fromDate)
        .lte("event_date", toDate)
        .in("credibility_score", ["confirmed", "likely"])
        .order("event_date", { ascending: false });

    const { data: events, error } = await query;

    if (error) {
        eventsContainer.innerHTML = '<div class="empty">Ошибка загрузки.</div>';
        console.error(error);
        return;
    }

    if (!events || events.length === 0) {
        eventsContainer.innerHTML = '<div class="empty">Нет важных событий за неделю.</div>';
        return;
    }

    await loadArticlesForEvents(events);

    // Sort by source count within each date
    events.sort((a, b) => {
        if (a.event_date !== b.event_date) return a.event_date < b.event_date ? 1 : -1;
        return (b.articles?.length || 0) - (a.articles?.length || 0);
    });

    renderWeekEvents(events);
}

async function loadArticlesForEvents(events) {
    for (const event of events) {
        const { data: links } = await db
            .from("event_articles")
            .select("article_id")
            .eq("event_id", event.id);

        if (links && links.length > 0) {
            const articleIds = links.map((l) => l.article_id);
            const { data: articles } = await db
                .from("articles")
                .select("*")
                .in("id", articleIds);
            event.articles = articles || [];
        } else {
            event.articles = [];
        }
    }
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

function renderWeekEvents(events) {
    eventsContainer.innerHTML = "";

    // Group by date
    const byDate = {};
    for (const event of events) {
        const d = event.event_date;
        if (!byDate[d]) byDate[d] = [];
        byDate[d].push(event);
    }

    for (const [date, dateEvents] of Object.entries(byDate)) {
        const header = document.createElement("div");
        header.className = "date-group-header";
        header.textContent = formatDateRu(date);
        eventsContainer.appendChild(header);

        for (const event of dateEvents) {
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
}

function renderEventCard(event) {
    const score = event.credibility_score || "unverified";
    const scoreLabel = CRED_LABELS[score] || score;
    const sourceCount = event.articles ? event.articles.length : 0;
    const sourcesWord = pluralSources(sourceCount);

    let analysisHtml = "";
    if (event.coverage_analysis) {
        const sources = event.coverage_analysis;
        let sourceSections = "";
        for (const [sourceName, info] of Object.entries(sources)) {
            sourceSections += `
                <div class="source-analysis">
                    <h4>${sourceName}</h4>
                    <div class="tone">Тон: ${info.tone || "н/д"}</div>
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
        linksHtml = `<div class="article-links"><h4>Источники</h4>${links}</div>`;
    }

    return `
        <div class="event-header">
            <span class="credibility-dot ${score}"></span>
            <span class="event-title">${event.title}</span>
        </div>
        <div class="event-meta">
            <span>${sourceCount} ${sourcesWord}</span>
            <span class="badge ${score}">${scoreLabel}</span>
        </div>
        <div class="event-summary">${event.summary || ""}</div>
        <div class="event-analysis">
            ${analysisHtml}
            ${event.credibility_reasoning ? `
                <div class="credibility-section">
                    <h4>Оценка достоверности</h4>
                    <p>${event.credibility_reasoning}</p>
                </div>` : ""}
            ${linksHtml}
        </div>`;
}

function pluralSources(n) {
    if (n === 1) return "источник";
    if (n >= 2 && n <= 4) return "источника";
    return "источников";
}

// --- Navigation ---

function updateNavButtons() {
    currentDateEl.textContent = formatDateRu(currentDate);

    const idx = availableDates.indexOf(currentDate);
    nextDayBtn.disabled = idx <= 0;
    prevDayBtn.disabled = idx >= availableDates.length - 1;
}

function formatDateRu(dateStr) {
    const d = new Date(dateStr + "T00:00:00");
    return d.toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" });
}

function setView(view) {
    currentView = view;
    if (view === "week") {
        controlsEl.classList.add("hidden");
        fetchWeekEvents();
    } else {
        controlsEl.classList.remove("hidden");
        fetchAvailableDates().then(fetchEvents);
    }
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
        // View tab (week)
        if (tab.dataset.view === "week") {
            document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
            tab.classList.add("active");
            setView("week");
            return;
        }

        // Category tab
        document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        currentCategory = tab.dataset.category;
        setView("daily");
    });
});

// --- Filters ---

credibilityFilter.addEventListener("change", () => {
    if (currentView === "week") fetchWeekEvents();
    else fetchEvents();
});

topOnlyToggle.addEventListener("change", () => {
    if (currentView === "week") fetchWeekEvents();
    else fetchEvents();
});

// --- Init ---

fetchAvailableDates().then(fetchEvents);
