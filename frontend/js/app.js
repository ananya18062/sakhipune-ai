// app.js — SakhiPune AI frontend logic
// Sends user queries to POST /recommend and displays support resources

// ── Config ────────────────────────────────────────────────────────────────────
// API base URL strategy:
//   - On Vercel:  empty string "" → same-origin relative calls (/api/recommend)
//   - Local dev:  set to "http://127.0.0.1:8000" if the backend runs separately
//
// Vercel routes /api/* to the FastAPI serverless function (see vercel.json).
// When running locally with  uvicorn  on port 8000, override by setting
// window.__SAKHIPUNE_API__ before this script loads, or keep the fallback below.
const API_BASE = (function () {
    // Allow runtime override (e.g. for local dev without modifying this file)
    if (typeof window.__SAKHIPUNE_API__ !== "undefined") {
        return window.__SAKHIPUNE_API__;
    }
    // On Vercel the frontend and API are on the same domain → use relative path
    // On local http.server (port 8080) the API is on a different port → use absolute
    const isLocal = window.location.hostname === "127.0.0.1" ||
                    window.location.hostname === "localhost";
    const isFileProtocol = window.location.protocol === "file:";
    if (isLocal || isFileProtocol) {
        return "http://127.0.0.1:8000";
    }
    // Production / Vercel: same-origin, API is under /api prefix
    return "";
}());

// ── API path helper ───────────────────────────────────────────────────────────
// On Vercel: API_BASE="" and all FastAPI routes are mounted under /api
// Locally:   API_BASE="http://127.0.0.1:8000" and routes are at root (no /api prefix)
function apiPath(route) {
    if (API_BASE === "") {
        // Vercel same-origin: prepend /api prefix
        return "/api" + route;
    }
    // Local: use the full base URL with the existing route
    return API_BASE + route;
}

const form           = document.getElementById("query-form");
const input          = document.getElementById("user-query");
const validationMsg  = document.getElementById("validation-msg");
const loadingMsg     = document.getElementById("loading-msg");
const resultsSection = document.getElementById("results-section");
const submitBtn      = document.getElementById("submit-btn");
const categoryButtons = document.querySelectorAll(".category-card");
const continueBtn = document.getElementById("continue-btn");
const categoryValidation = document.getElementById("category-validation");
const questionsPanel = document.getElementById("questions-panel");
const queryCard = document.querySelector(".query-card");
const languageSelector = document.getElementById("language-selector");
const loginButton = document.getElementById("login-button");
const loginModal = document.getElementById("login-modal");
const closeLogin = document.getElementById("close-login");
const loginForm = document.getElementById("login-form");
const loginValidation = document.getElementById("login-validation");
const voiceButton = document.getElementById("voice-button");
const voiceStatus = document.getElementById("voice-status");
let selectedCategory = null;
let selectedAnswers = {};
let selectedLanguage = languageSelector.value;
let speechRecognition = null;
let voiceBaseText = "";
let lastSupportRequest = null;

languageSelector.addEventListener("change", function () {
    selectedLanguage = languageSelector.value;
    document.documentElement.lang = selectedLanguage;
    if (speechRecognition) {
        speechRecognition.lang = getSpeechLanguage(selectedLanguage);
    }
});

function getSpeechLanguage(language) {
    return { en: "en-IN", hi: "hi-IN", mr: "mr-IN" }[language] || "en-IN";
}

function setVoiceStatus(message) {
    voiceStatus.textContent = message;
}

function setupVoiceRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        voiceButton.disabled = true;
        setVoiceStatus("Voice input is not supported in this browser.");
        return;
    }

    speechRecognition = new SpeechRecognition();
    speechRecognition.continuous = false;
    speechRecognition.interimResults = false;
    speechRecognition.maxAlternatives = 3;
    speechRecognition.lang = getSpeechLanguage(selectedLanguage);

    speechRecognition.onstart = function () {
        voiceBaseText = input.value.trim();
        voiceButton.classList.add("is-listening");
        voiceButton.setAttribute("aria-pressed", "true");
        voiceButton.innerHTML = '<span aria-hidden="true">&#9632;</span> Listening...';
        setVoiceStatus("Speak your question now.");
    };

    speechRecognition.onresult = function (event) {
        const result = event.results[event.resultIndex];
        const alternatives = Array.from(result || []);
        const best = alternatives.sort(function (left, right) {
            return (right.confidence || 0) - (left.confidence || 0);
        })[0];
        const transcript = best ? best.transcript.trim().replace(/\s+/g, " ") : "";
        if (transcript) {
            input.value = [voiceBaseText, transcript].filter(Boolean).join(" ");
            setVoiceStatus("Voice captured. Review your question before submitting.");
        }
        clearValidationError();
    };

    speechRecognition.onnomatch = function () {
        setVoiceStatus("No clear speech was detected. Please try again.");
    };

    speechRecognition.onerror = function (event) {
        const message = event.error === "not-allowed"
            ? "Microphone permission was not granted."
            : "Voice input could not be understood. Please try again.";
        setVoiceStatus(message);
    };

    speechRecognition.onend = function () {
        voiceButton.classList.remove("is-listening");
        voiceButton.setAttribute("aria-pressed", "false");
        voiceButton.innerHTML = '<span aria-hidden="true">&#127908;</span> Ask by voice';
    };

    voiceButton.addEventListener("click", function () {
        if (voiceButton.classList.contains("is-listening")) {
            speechRecognition.stop();
            return;
        }
        setVoiceStatus("");
        speechRecognition.lang = getSpeechLanguage(selectedLanguage);
        speechRecognition.start();
    });
}

setupVoiceRecognition();

function openLoginModal() {
    loginModal.hidden = false;
    document.getElementById("login-name").focus();
}

function closeLoginModal() {
    loginModal.hidden = true;
    loginValidation.textContent = "";
}

function updateSessionButton() {
    const sessionName = sessionStorage.getItem("sakhipune_session_name");
    loginButton.textContent = sessionName ? "Log out" : "Sign in";
    loginButton.setAttribute("aria-label", sessionName ? "Log out" : "Sign in");
}

loginButton.addEventListener("click", function () {
    if (sessionStorage.getItem("sakhipune_session_name")) {
        sessionStorage.removeItem("sakhipune_session_name");
        updateSessionButton();
        return;
    }
    openLoginModal();
});
closeLogin.addEventListener("click", closeLoginModal);
loginModal.addEventListener("click", function (event) {
    if (event.target === loginModal) {
        closeLoginModal();
    }
});

loginForm.addEventListener("submit", function (event) {
    event.preventDefault();
    const name = document.getElementById("login-name").value.trim();
    const email = document.getElementById("login-email").value.trim();
    if (!name || !email || !loginForm.checkValidity()) {
        loginValidation.textContent = "Please enter your name and a valid email address.";
        return;
    }
    sessionStorage.setItem("sakhipune_session_name", name);
    updateSessionButton();
    closeLoginModal();
});

updateSessionButton();

// Category selection only prepares the next step; it does not call the API.
categoryButtons.forEach(function (button) {
    button.addEventListener("click", function () {
        selectedCategory = {
            name: button.dataset.category,
            query: button.dataset.query || "",
        };
        selectedAnswers = {};
        input.value = "";
        questionsPanel.replaceChildren();
        questionsPanel.hidden = true;
        queryCard.classList.remove("has-questions");

        categoryButtons.forEach(function (categoryButton) {
            const isSelected = categoryButton === button;
            categoryButton.classList.toggle("is-selected", isSelected);
            categoryButton.setAttribute("aria-pressed", isSelected ? "true" : "false");
        });
        categoryValidation.textContent = "";
    });
});

continueBtn.addEventListener("click", function () {
    if (!selectedCategory) {
        categoryValidation.textContent = "Please select a support category to continue.";
        return;
    }

    const questionForm = renderQuestions(selectedCategory.name, questionsPanel);
    queryCard.classList.add("has-questions");
    questionForm.addEventListener("questions-complete", function (event) {
        const questions = getQuestionsForCategory(selectedCategory.name);
        const answers = event.detail.answers;
        if (!validateAnswers(questions, answers)) {
            return;
        }

        selectedAnswers = answers;
        input.value = buildSupportQuery(selectedCategory.query, answers);
        clearValidationError();
        input.focus();
        document.getElementById("query-heading").scrollIntoView({ behavior: "smooth", block: "center" });
    });
    questionForm.addEventListener("questions-back", function () {
        questionsPanel.hidden = true;
        queryCard.classList.remove("has-questions");
        document.getElementById("explore").scrollIntoView({ behavior: "smooth", block: "center" });
    });

    questionsPanel.scrollIntoView({ behavior: "smooth", block: "center" });
});

function buildSupportQuery(categoryQuery, answers) {
    const answerSummary = Object.keys(answers)
        .map(function (key) { return answers[key]; })
        .join(", ");
    return categoryQuery + ". My preferences are: " + answerSummary + ".";
}

/**
 * Builds the structured request kept in frontend memory before API integration.
 * @returns {{message: string, category: string, preferences: object, language: string}}
 */
function buildSupportRequest() {
    return {
        message: input.value.trim(),
        category: selectedCategory ? getCategoryKey(selectedCategory.name) : "",
        preferences: Object.assign({}, selectedAnswers),
        language: selectedLanguage,
    };
}

/**
 * Validates the structured support request without storing personal information.
 * @param {object} request
 * @returns {{valid: boolean, errors: string[]}}
 */
function validateSupportRequest(request) {
    const errors = [];

    if (!request.category) {
        errors.push("Please select a support category to continue.");
    }
    if (!request.message) {
        errors.push("Please describe what you need help with.");
    }

    const questions = getQuestionsForCategory(request.category);
    questions.forEach(function (question) {
        if (!request.preferences[question.id]) {
            errors.push("Please complete the required questions.");
        }
    });

    return { valid: errors.length === 0, errors: errors };
}

/**
 * Clears the current support flow from the page and frontend memory.
 */
function resetSupportFlow() {
    selectedCategory = null;
    selectedAnswers = {};
    input.value = "";
    clearValidationError();
    categoryValidation.textContent = "";
    questionsPanel.replaceChildren();
    questionsPanel.hidden = true;
    queryCard.classList.remove("has-questions");
    categoryButtons.forEach(function (button) {
        button.classList.remove("is-selected");
        button.setAttribute("aria-pressed", "false");
    });
}

// ── Form submit handler ───────────────────────────────────────────────────────

form.addEventListener("submit", async function (event) {
    event.preventDefault();

    const supportRequest = buildSupportRequest();
    const validation = validateSupportRequest(supportRequest);
    if (!validation.valid) {
        showValidationError(validation.errors[0]);
        input.focus();
        return;
    }

    clearValidationError();
    lastSupportRequest = supportRequest;
    setLoadingState(true);
    try {
        await fetchRecommendations(supportRequest);
    } finally {
        setLoadingState(false);
    }
});

// Clear validation error as soon as the user starts typing again
input.addEventListener("input", function () {
    if (input.value.trim()) {
        clearValidationError();
    }
});

// ── Core fetch function ───────────────────────────────────────────────────────

/**
 * POSTs the structured support request to the existing /recommend endpoint.
 * On success, renders the intent summary + resource cards.
 * On failure, renders a friendly, specific error message.
 *
 * Error categories handled separately:
 *   - Network / backend unreachable  → "SakhiPune AI is temporarily unavailable"
 *   - 422 Validation error           → "Please check your query and try again"
 *   - 503 Service unavailable        → "SakhiPune AI is temporarily unavailable"
 *   - Other 4xx / 5xx               → "Something went wrong. Please try again."
 *   - Malformed JSON response        → "Unexpected response" (logged to console)
 *   - Empty recommendations list     → friendly no-results message
 *
 * @param {object} supportRequest
 */
async function fetchRecommendations(supportRequest) {
    let response;
    try {
        response = await fetch(apiPath("/recommend"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(supportRequest),
        });
    } catch (networkError) {
        // fetch() itself threw — backend is unreachable (not started, wrong port, CORS preflight blocked)
        console.error("[SakhiPune] Network error:", networkError);
        showErrorResult(
            "SakhiPune AI is temporarily unavailable. " +
            "Please make sure the backend server is running and try again."
        );
        return;
    }

    // Backend responded — check HTTP status before parsing body
    if (!response.ok) {
        let errorBody = null;
        try { errorBody = await response.json(); } catch (_) { /* non-JSON error body */ }

        console.warn("[SakhiPune] HTTP", response.status, errorBody);

        if (response.status === 422) {
            const detail = errorBody && errorBody.message
                ? errorBody.message
                : "Please check your query and try again.";
            showErrorResult(detail);
            return;
        }
        if (response.status === 503) {
            showErrorResult("SakhiPune AI is temporarily unavailable. Please try again shortly.");
            return;
        }
        showErrorResult("Something went wrong. Please try again.");
        return;
    }

    // Parse JSON
    let data;
    try {
        data = await response.json();
    } catch (parseError) {
        console.error("[SakhiPune] JSON parse error:", parseError);
        showErrorResult("We received an unexpected response. Please try again.");
        return;
    }

    // Guard: ensure required fields are present
    if (!data.intent || data.confidence === undefined || !Array.isArray(data.recommendations)) {
        console.error("[SakhiPune] Unexpected response shape:", data);
        showErrorResult("We received an unexpected response. Please try again.");
        return;
    }

    renderResults(data);
}

// ── Render functions ──────────────────────────────────────────────────────────

/**
 * Renders the full results area:
 *   - Intent summary bar (detected need + confidence)
 *   - One resource card per recommendation
 *   - "No results" message if recommendations list is empty
 *
 * Uses safe DOM manipulation — no raw user text injected via innerHTML.
 *
 * @param {object} data - { message, intent, confidence, recommendations }
 */
function renderResults(data) {
    // Clear previous results using safe DOM method
    resultsSection.replaceChildren();

    const successMessage = document.createElement("p");
    successMessage.className = "results-success";
    successMessage.textContent = "Here are support options that match your needs.";
    resultsSection.appendChild(successMessage);

    // ── Intent summary card ───────────────────────────────────────────────────
    const summaryCard = document.createElement("div");
    summaryCard.className = "intent-summary";

    const needLabel = document.createElement("span");
    needLabel.className = "intent-summary__label";
    needLabel.textContent = "Detected Need:";

    const needValue = document.createElement("span");
    needValue.className = "intent-summary__value";
    needValue.textContent = formatIntent(data.intent);

    const scoreLabel = document.createElement("span");
    scoreLabel.className = "intent-summary__label";
    scoreLabel.textContent = "Match Score:";

    const scoreValue = document.createElement("span");
    scoreValue.className = "intent-summary__value";
    const matchScore = data.match_score !== undefined
        ? data.match_score
        : (data.recommendations[0] && data.recommendations[0].score) || 0;
    scoreValue.textContent = Math.round(matchScore * 100) + "%";

    summaryCard.appendChild(needLabel);
    summaryCard.appendChild(needValue);
    summaryCard.appendChild(scoreLabel);
    summaryCard.appendChild(scoreValue);
    resultsSection.appendChild(summaryCard);

    // ── Resource cards or "no results" message ────────────────────────────────
    if (data.recommendations.length === 0) {
        const noResult = document.createElement("div");
        noResult.className = "result-card result-card--empty";
        const msg = document.createElement("p");
        msg.textContent = "No matching support resources were found for your query. Try rephrasing or selecting a different category.";
        noResult.appendChild(msg);
        resultsSection.appendChild(noResult);
        resultsSection.appendChild(buildRecoveryActions());
        return;
    }

    data.recommendations.forEach(function (resource) {
        resultsSection.appendChild(buildResourceCard(resource));
    });

    resultsSection.appendChild(buildStartAgainButton());
}

/**
 * Builds a single resource card element using safe DOM methods.
 * No innerHTML used for user-supplied or DB-supplied text.
 *
 * @param {object} resource - { name, category, description, location, contact }
 * @returns {HTMLElement}
 */
function buildResourceCard(resource) {
    const card = document.createElement("div");
    card.className = "result-card resource-card";

    // Name / title
    const name = document.createElement("h3");
    name.className = "resource-card__name";
    name.textContent = resource.name || "Unnamed Resource";
    card.appendChild(name);

    // Category badge
    const badge = document.createElement("span");
    badge.className = "resource-card__badge";
    badge.textContent = resource.category || "";
    card.appendChild(badge);

    if (resource.score !== undefined && resource.score !== null) {
        const score = document.createElement("span");
        score.className = "resource-card__score";
        score.textContent = "Match score " + Math.round(resource.score * 100) + "%";
        card.appendChild(score);
    }

    // Description
    if (resource.description) {
        const desc = document.createElement("p");
        desc.className = "resource-card__description";
        desc.textContent = resource.description;
        card.appendChild(desc);
    }

    if (resource.reason) {
        const reason = document.createElement("p");
        reason.className = "resource-card__reason";
        reason.textContent = resource.reason;
        card.appendChild(reason);
    }

    // Location
    if (resource.location) {
        const loc = buildDetailRow("📍", resource.location);
        card.appendChild(loc);
    }

    // Contact
    if (resource.contact) {
        const con = buildDetailRow("📞", resource.contact);
        card.appendChild(con);
        card.appendChild(buildContactAction(resource.contact));
    }

    return card;
}

/**
 * Creates a contact action only from contact information supplied by the API.
 * @param {string} contact
 * @returns {HTMLAnchorElement}
 */
function buildContactAction(contact) {
    const action = document.createElement("a");
    action.className = "resource-card__action";
    action.textContent = "Contact resource";

    const trimmedContact = contact.trim();
    if (/^https?:\/\//i.test(trimmedContact)) {
        action.href = trimmedContact;
        action.target = "_blank";
        action.rel = "noopener noreferrer";
    } else if (/^[+\d][\d\s().,-]{2,}$/.test(trimmedContact)) {
        // Matches full numbers (e.g. +91-20-26128000) and short emergency codes (100, 108, 181, 1091)
        action.href = "tel:" + trimmedContact.replace(/[^+\d]/g, "");
    } else if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmedContact)) {
        action.href = "mailto:" + trimmedContact;
    } else {
        action.removeAttribute("href");
        action.setAttribute("aria-disabled", "true");
        action.classList.add("resource-card__action--text");
    }

    return action;
}

function buildStartAgainButton() {
    const action = document.createElement("button");
    action.type = "button";
    action.className = "start-again-button";
    action.textContent = "Start Again";
    action.addEventListener("click", function () {
        resetSupportFlow();
        resultsSection.replaceChildren();
        document.getElementById("explore").scrollIntoView({ behavior: "smooth", block: "start" });
    });
    return action;
}

function buildRecoveryActions() {
    const actions = document.createElement("div");
    actions.className = "result-actions";

    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "start-again-button";
    retry.textContent = "Try Again";
    retry.addEventListener("click", async function () {
        if (!lastSupportRequest || submitBtn.disabled) return;
        setLoadingState(true);
        try {
            await fetchRecommendations(lastSupportRequest);
        } finally {
            setLoadingState(false);
        }
    });

    const choose = document.createElement("button");
    choose.type = "button";
    choose.className = "start-again-button start-again-button--secondary";
    choose.textContent = "Choose Another Category";
    choose.addEventListener("click", function () {
        resetSupportFlow();
        resultsSection.replaceChildren();
        document.getElementById("explore").scrollIntoView({ behavior: "smooth", block: "start" });
    });

    actions.appendChild(retry);
    actions.appendChild(choose);
    return actions;
}

/**
 * Creates a small detail row with an icon and text.
 * @param {string} icon   - Emoji icon
 * @param {string} text   - Detail text
 * @returns {HTMLElement}
 */
function buildDetailRow(icon, text) {
    const row = document.createElement("p");
    row.className = "resource-card__detail";

    const iconSpan = document.createElement("span");
    iconSpan.setAttribute("aria-hidden", "true");
    iconSpan.textContent = icon + " ";

    const textNode = document.createTextNode(text);

    row.appendChild(iconSpan);
    row.appendChild(textNode);
    return row;
}

// ── Generic display helpers ───────────────────────────────────────────────────

/**
 * Renders a user-friendly error card. No stack traces or raw errors shown.
 * @param {string} message
 */
function showErrorResult(message) {
    resultsSection.replaceChildren();
    const card = document.createElement("div");
    card.className = "result-card result-card--error";
    const p = document.createElement("p");
    p.textContent = message;
    card.appendChild(p);
    resultsSection.appendChild(card);
    resultsSection.appendChild(buildStartAgainButton());
}

/**
 * Shows/hides the loading indicator and disables/enables the submit button.
 * @param {boolean} isLoading
 */
function setLoadingState(isLoading) {
    loadingMsg.hidden     = !isLoading;
    submitBtn.disabled    = isLoading;
    submitBtn.setAttribute("aria-label", isLoading ? "Finding support, please wait" : "Find My Support");
    // Clear then rebuild button content with safe DOM methods
    submitBtn.textContent = "";
    const icon = document.createElement("span");
    icon.setAttribute("aria-hidden", "true");
    if (isLoading) {
        const spinner = document.createElement("span");
        spinner.className = "button-spinner";
        spinner.setAttribute("aria-hidden", "true");
        submitBtn.appendChild(spinner);
        submitBtn.appendChild(document.createTextNode(" Finding support..."));
    } else {
        icon.textContent = "\u2728";
        submitBtn.appendChild(icon);
        submitBtn.appendChild(document.createTextNode(" Find My Support"));
    }
    resultsSection.setAttribute("aria-busy", isLoading ? "true" : "false");
}

/**
 * Shows a validation error below the input field.
 * @param {string} message
 */
function showValidationError(message) {
    validationMsg.textContent = message;
    input.style.borderColor   = "#c62828";
}

/**
 * Clears the validation error and resets the input border.
 */
function clearValidationError() {
    validationMsg.textContent = "";
    input.style.borderColor   = "";
}

/**
 * Converts a snake_case intent into a readable label.
 * "domestic_violence" → "Domestic Violence"
 * @param {string} intent
 * @returns {string}
 */
function formatIntent(intent) {
    return intent
        .split("_")
        .map(function (word) { return word.charAt(0).toUpperCase() + word.slice(1); })
        .join(" ");
}
