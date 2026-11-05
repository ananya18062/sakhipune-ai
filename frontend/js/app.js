// app.js — SakhiPune AI frontend logic
// Chat interface, domain selection, query editing, and follow-up context.

// ── API config ────────────────────────────────────────────────────────────────
const API_BASE = (function () {
    if (typeof window.__SAKHIPUNE_API__ !== "undefined") return window.__SAKHIPUNE_API__;
    const isLocal = window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost";
    const isFileProtocol = window.location.protocol === "file:";
    return (isLocal || isFileProtocol) ? "http://127.0.0.1:8000" : "";
}());

function apiPath(route) {
    return API_BASE + "/api" + route;
}

// ── DOM refs ──────────────────────────────────────────────────────────────────
const form              = document.getElementById("query-form");
const input             = document.getElementById("user-query");
const validationMsg     = document.getElementById("validation-msg");
const loadingMsg        = document.getElementById("loading-msg");
const resultsSection    = document.getElementById("results-section");
const submitBtn         = document.getElementById("submit-btn");
const categoryButtons   = document.querySelectorAll(".category-card");
const continueBtn       = document.getElementById("continue-btn");
const categoryValidation = document.getElementById("category-validation");
const questionsPanel    = document.getElementById("questions-panel");
const queryCard         = document.querySelector(".query-card");
const languageSelector  = document.getElementById("language-selector");
const loginButton       = document.getElementById("login-button");
const loginModal        = document.getElementById("login-modal");
const closeLogin        = document.getElementById("close-login");
const loginForm         = document.getElementById("login-form");
const loginValidation   = document.getElementById("login-validation");
const voiceButton       = document.getElementById("voice-button");
const voiceStatus       = document.getElementById("voice-status");

// ── Conversation state ────────────────────────────────────────────────────────
// This is the single source of truth for the current chat session.
let conversationState = {
    turns: [],           // { role, content, request, response } objects
    selectedCategory: null,
    selectedAnswers: {},
    selectedLanguage: "en",
    accumulatedFilters: {},
    lastIntent: null,
    lastQuery: null,
    editingTurnIndex: null,  // non-null when user is editing a previous message
};

function resetConversation() {
    conversationState = {
        turns: [],
        selectedCategory: null,
        selectedAnswers: {},
        selectedLanguage: languageSelector.value || "en",
        accumulatedFilters: {},
        lastIntent: null,
        lastQuery: null,
        editingTurnIndex: null,
    };
    categoryButtons.forEach(function (b) {
        b.classList.remove("is-selected");
        b.setAttribute("aria-pressed", "false");
    });
    categoryValidation.textContent = "";
    questionsPanel.replaceChildren();
    questionsPanel.hidden = true;
    queryCard.classList.remove("has-questions");
    input.value = "";
    clearValidationError();
    resultsSection.replaceChildren();
    const existingBar = document.getElementById("active-filters-bar");
    if (existingBar) existingBar.remove();
    renderChatHistory();
}

// ── Active filter display ─────────────────────────────────────────────────────
// Shows a chip bar of current active filters below the query card.
// Each chip has a × button to remove that specific filter.

const FILTER_LABELS = {
    work_mode_filter: { remote: "Remote", hybrid: "Hybrid", on_site: "On-site" },
    experience_filter: { fresher: "Fresher", "1_2_years": "1–2 yrs exp", "3_5_years": "3–5 yrs exp", any: "Any level" },
    employment_type_filter: { full_time: "Full-time", part_time: "Part-time", contract: "Contract", apprenticeship: "Internship/Apprenticeship", self_employment: "Self-employment" },
    scheme_type: { government: "Government schemes" },
    cost_preference: { free: "Free only" },
};

const FILTER_NAMES = {
    work_mode_filter: "Work mode",
    experience_filter: "Experience",
    employment_type_filter: "Employment type",
    scheme_type: "Scheme type",
    cost_preference: "Cost",
    interest_area: "Field",
    support_type: "Support type",
};

function getFilterChipLabel(key, value) {
    if (FILTER_LABELS[key] && FILTER_LABELS[key][value]) return FILTER_LABELS[key][value];
    const name = FILTER_NAMES[key] || key.replace(/_/g, " ");
    return name + ": " + value;
}

function renderActiveFilters() {
    let bar = document.getElementById("active-filters-bar");
    const filters = conversationState.accumulatedFilters;

    // Collect displayable filters (skip internal keys like _last_intent)
    const displayable = Object.entries(filters).filter(function (entry) {
        return !entry[0].startsWith("_") && entry[1];
    });

    // Remove bar if no filters
    if (displayable.length === 0) {
        if (bar) bar.remove();
        return;
    }

    if (!bar) {
        bar = document.createElement("div");
        bar.id = "active-filters-bar";
        bar.className = "active-filters-bar";
        bar.setAttribute("aria-label", "Active search filters");
        // Insert just above the query form
        queryCard.insertBefore(bar, form);
    }

    bar.replaceChildren();

    const label = document.createElement("span");
    label.className = "active-filters-label";
    label.textContent = "Active filters:";
    bar.appendChild(label);

    displayable.forEach(function (entry) {
        const key = entry[0];
        const value = entry[1];
        const chip = document.createElement("span");
        chip.className = "filter-chip";

        const chipText = document.createElement("span");
        chipText.className = "filter-chip__text";
        chipText.textContent = getFilterChipLabel(key, value);
        chip.appendChild(chipText);

        const removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.className = "filter-chip__remove";
        removeBtn.setAttribute("aria-label", "Remove filter: " + getFilterChipLabel(key, value));
        removeBtn.textContent = "\u00D7";
        removeBtn.addEventListener("click", function () {
            delete conversationState.accumulatedFilters[key];
            // Also remove from selectedAnswers if it came from there
            const answerKey = Object.keys(conversationState.selectedAnswers).find(function (k) {
                return k === key || k.replace("_filter", "") === key;
            });
            if (answerKey) delete conversationState.selectedAnswers[answerKey];
            renderActiveFilters();
        });
        chip.appendChild(removeBtn);
        bar.appendChild(chip);
    });

    // Clear all button
    const clearAll = document.createElement("button");
    clearAll.type = "button";
    clearAll.className = "filter-chip filter-chip--clear";
    clearAll.textContent = "Clear all";
    clearAll.addEventListener("click", function () {
        conversationState.accumulatedFilters = {};
        conversationState.selectedAnswers = {};
        renderActiveFilters();
    });
    bar.appendChild(clearAll);
}

// ── Language ──────────────────────────────────────────────────────────────────
languageSelector.addEventListener("change", function () {
    conversationState.selectedLanguage = languageSelector.value;
    document.documentElement.lang = languageSelector.value;
    if (speechRecognition) speechRecognition.lang = getSpeechLanguage(languageSelector.value);
});

function getSpeechLanguage(lang) {
    return { en: "en-IN", hi: "hi-IN", mr: "mr-IN" }[lang] || "en-IN";
}

// ── Voice ─────────────────────────────────────────────────────────────────────
let speechRecognition = null;
let voiceBaseText = "";

function setVoiceStatus(msg) { voiceStatus.textContent = msg; }

function setupVoiceRecognition() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { voiceButton.disabled = true; setVoiceStatus("Voice input is not supported in this browser."); return; }
    speechRecognition = new SR();
    speechRecognition.continuous = false;
    speechRecognition.interimResults = false;
    speechRecognition.maxAlternatives = 3;
    speechRecognition.lang = getSpeechLanguage(conversationState.selectedLanguage);

    speechRecognition.onstart = function () {
        voiceBaseText = input.value.trim();
        voiceButton.classList.add("is-listening");
        voiceButton.setAttribute("aria-pressed", "true");
        voiceButton.innerHTML = '<span aria-hidden="true">&#9632;</span> Listening...';
        setVoiceStatus("Speak your question now.");
    };
    speechRecognition.onresult = function (event) {
        const result = event.results[event.resultIndex];
        const best = Array.from(result || []).sort(function (a, b) { return (b.confidence || 0) - (a.confidence || 0); })[0];
        const transcript = best ? best.transcript.trim().replace(/\s+/g, " ") : "";
        if (transcript) {
            input.value = [voiceBaseText, transcript].filter(Boolean).join(" ");
            setVoiceStatus("Voice captured. Review your question before submitting.");
        }
        clearValidationError();
    };
    speechRecognition.onnomatch = function () { setVoiceStatus("No clear speech detected. Please try again."); };
    speechRecognition.onerror = function (event) {
        setVoiceStatus(event.error === "not-allowed" ? "Microphone permission was not granted." : "Voice input could not be understood. Please try again.");
    };
    speechRecognition.onend = function () {
        voiceButton.classList.remove("is-listening");
        voiceButton.setAttribute("aria-pressed", "false");
        voiceButton.innerHTML = '<span aria-hidden="true">&#127908;</span> Ask by voice';
    };
    voiceButton.addEventListener("click", function () {
        if (voiceButton.classList.contains("is-listening")) { speechRecognition.stop(); return; }
        setVoiceStatus("");
        speechRecognition.lang = getSpeechLanguage(conversationState.selectedLanguage);
        speechRecognition.start();
    });
}
setupVoiceRecognition();

// ── Login modal ───────────────────────────────────────────────────────────────
function openLoginModal() { loginModal.hidden = false; document.getElementById("login-name").focus(); }
function closeLoginModal() { loginModal.hidden = true; loginValidation.textContent = ""; }

function updateSessionButton() {
    const name = sessionStorage.getItem("sakhipune_session_name");
    loginButton.textContent = name ? "Log out" : "Sign in";
    loginButton.setAttribute("aria-label", name ? "Log out" : "Sign in");
}

loginButton.addEventListener("click", function () {
    if (sessionStorage.getItem("sakhipune_session_name")) { sessionStorage.removeItem("sakhipune_session_name"); updateSessionButton(); return; }
    openLoginModal();
});
closeLogin.addEventListener("click", closeLoginModal);
loginModal.addEventListener("click", function (e) { if (e.target === loginModal) closeLoginModal(); });
loginForm.addEventListener("submit", function (e) {
    e.preventDefault();
    const name = document.getElementById("login-name").value.trim();
    const email = document.getElementById("login-email").value.trim();
    if (!name || !email || !loginForm.checkValidity()) { loginValidation.textContent = "Please enter your name and a valid email address."; return; }
    sessionStorage.setItem("sakhipune_session_name", name);
    updateSessionButton();
    closeLoginModal();
});
updateSessionButton();

// ── Category selection ────────────────────────────────────────────────────────
categoryButtons.forEach(function (button) {
    button.addEventListener("click", function () {
        conversationState.selectedCategory = {
            name: button.dataset.category,
            query: button.dataset.query || "",
        };
        // When domain changes, clear incompatible accumulated filters
        if (conversationState.lastIntent) {
            conversationState.accumulatedFilters = {};
        }
        conversationState.selectedAnswers = {};
        input.value = "";
        questionsPanel.replaceChildren();
        questionsPanel.hidden = true;
        queryCard.classList.remove("has-questions");

        categoryButtons.forEach(function (b) {
            const sel = b === button;
            b.classList.toggle("is-selected", sel);
            b.setAttribute("aria-pressed", sel ? "true" : "false");
        });
        categoryValidation.textContent = "";
    });
});

continueBtn.addEventListener("click", function () {
    if (!conversationState.selectedCategory) { categoryValidation.textContent = "Please select a support category to continue."; return; }
    const questionForm = renderQuestions(conversationState.selectedCategory.name, questionsPanel);
    queryCard.classList.add("has-questions");

    questionForm.addEventListener("questions-complete", function (event) {
        const questions = getQuestionsForCategory(conversationState.selectedCategory.name);
        const answers = event.detail.answers;
        const catKey = event.detail.categoryKey || getCategoryKey(conversationState.selectedCategory.name);
        conversationState.selectedAnswers = answers;

        // Extract typed backend filter fields from answers (e.g. work_mode_filter, experience_filter)
        const extractedFilters = {};
        Object.keys(answers).forEach(function (questionId) {
            const filter = getFilterFromAnswer(catKey, questionId, answers[questionId]);
            if (filter) {
                extractedFilters[filter.key] = filter.value;
            }
        });
        // Merge into accumulated filters
        Object.assign(conversationState.accumulatedFilters, extractedFilters);

        input.value = buildSupportQuery(conversationState.selectedCategory.query, answers);
        clearValidationError();
        renderActiveFilters();
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
    const summary = Object.values(answers).join(", ");
    return categoryQuery + ". My preferences are: " + summary + ".";
}

function getCategoryKey(category) {
    const n = String(category || "").toLowerCase().replace(/&/g, "and").replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
    const aliases = { education_and_scholarships: "education", legal_help: "legal", safety_and_emergency: "safety", government_schemes: "government_scheme" };
    return aliases[n] || n;
}

// ── Follow-up filter extraction ───────────────────────────────────────────────
// Parse explicit follow-up signals from short messages so we don't need an LLM.
function extractFollowUpFilters(message) {
    const m = message.toLowerCase();
    const filters = {};
    if (/remote|work from home|wfh/.test(m))    filters.work_mode_filter = "remote";
    if (/hybrid/.test(m))                         filters.work_mode_filter = "hybrid";
    if (/on.site|onsite|in.person|offline/.test(m)) filters.work_mode_filter = "on_site";
    if (/fresher|student|beginner|no experience/.test(m)) filters.experience_filter = "fresher";
    if (/experienced|senior/.test(m))             filters.experience_filter = "3_5_years";
    if (/free|no cost|without fee/.test(m))       filters.cost_preference = "free";
    if (/government|gov|sarkari|official/.test(m)) filters.scheme_type = "government";
    if (/part.time/.test(m))                      filters.employment_type_filter = "part_time";
    if (/full.time/.test(m))                      filters.employment_type_filter = "full_time";
    if (/internship/.test(m))                     filters.employment_type_filter = "apprenticeship";
    return filters;
}

// Detect if a message is a short follow-up refinement rather than a new query.
function isLikelyFollowUp(message) {
    const wordCount = message.trim().split(/\s+/).length;
    if (wordCount > 12) return false;  // long messages are likely new queries
    const followUpPhrases = [
        /^only /i, /^just /i, /^show (me )?(only|more)/i,
        /^any free/i, /^i am a /i, /^i'm a /i,
        /^remote$/i, /^hybrid$/i, /^on.site$/i,
        /^fresher$/i, /^experienced$/i,
        /^government (only|schemes)/i,
        /^(remove|clear|without) /i,
        /^more options/i, /^something else/i,
    ];
    return followUpPhrases.some(function (re) { return re.test(message.trim()); }) || wordCount <= 4;
}

// ── Form submission ───────────────────────────────────────────────────────────
form.addEventListener("submit", async function (event) {
    event.preventDefault();
    const message = input.value.trim();
    if (!message) { showValidationError("Please describe what you need help with."); input.focus(); return; }

    clearValidationError();

    // Determine if this is a follow-up or a new/edited query
    const isEditing = conversationState.editingTurnIndex !== null;
    const hasHistory = conversationState.turns.length > 0;
    const isFollowUp = !isEditing && hasHistory && isLikelyFollowUp(message);

    // Extract any explicit filter signals from the message
    const newFilters = extractFollowUpFilters(message);
    if (isFollowUp) {
        // Merge new filters into accumulated state
        Object.assign(conversationState.accumulatedFilters, newFilters);
        renderActiveFilters();
    } else if (!isEditing) {        // New query — keep category but reset filters unless they come from questions
        conversationState.accumulatedFilters = Object.assign({}, newFilters);
    }

    const request = buildChatRequest(message, isFollowUp);
    await submitChatRequest(request, message, isEditing, isFollowUp);
});

input.addEventListener("input", function () { if (input.value.trim()) clearValidationError(); });

function buildChatRequest(message, isFollowUp) {
    const state = conversationState;
    const prefs = Object.assign({}, state.selectedAnswers, state.accumulatedFilters);

    // Build conversation state to send to the backend
    const backendState = {
        intent: state.lastIntent,
        last_query: state.lastQuery,
        filters: state.accumulatedFilters,
    };

    return {
        message: message,
        category: state.selectedCategory ? getCategoryKey(state.selectedCategory.name) : null,
        language: state.selectedLanguage,
        preferences: Object.keys(prefs).length ? prefs : null,
        conversation_state: (state.lastIntent || state.lastQuery) ? backendState : null,
        is_followup: isFollowUp,
    };
}

async function submitChatRequest(request, userMessage, isEditing, isFollowUp) {
    // If editing, truncate conversation history from the edited turn
    if (isEditing) {
        conversationState.turns = conversationState.turns.slice(0, conversationState.editingTurnIndex);
        conversationState.editingTurnIndex = null;
    }

    // Add user turn to history
    const userTurn = { role: "user", content: userMessage, isFollowUp: isFollowUp };
    conversationState.turns.push(userTurn);
    conversationState.lastQuery = userMessage;

    setLoadingState(true);
    renderChatHistory();

    try {
        const response = await fetch(apiPath("/chat"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(request),
        });

        if (!response.ok) {
            let errorBody = null;
            try { errorBody = await response.json(); } catch (_) {}
            const msg = (response.status === 422 && errorBody && errorBody.message)
                ? errorBody.message
                : response.status === 503
                    ? "SakhiPune AI is temporarily unavailable. Please try again shortly."
                    : "Something went wrong. Please try again.";
            conversationState.turns.push({ role: "assistant", content: msg, isError: true, recommendations: [] });
            conversationState.lastIntent = null;
        } else {
            const data = await response.json();
            if (!data.intent || !Array.isArray(data.recommendations)) {
                conversationState.turns.push({ role: "assistant", content: "We received an unexpected response. Please try again.", isError: true, recommendations: [] });
            } else {
                conversationState.lastIntent = data.intent;
                // Update accumulated filters with any detected intent
                if (data.intent && data.intent !== "general") {
                    conversationState.accumulatedFilters._last_intent = data.intent;
                }
                const assistantContent = buildAssistantMessage(data, isFollowUp);
                conversationState.turns.push({
                    role: "assistant",
                    content: assistantContent,
                    isError: false,
                    recommendations: data.recommendations,
                    intent: data.intent,
                    confidence: data.confidence,
                    matchScore: data.match_score,
                    isFollowUp: isFollowUp,
                });
            }
        }
    } catch (networkError) {
        console.error("[SakhiPune] Network error:", networkError);
        conversationState.turns.push({
            role: "assistant",
            content: "SakhiPune AI is temporarily unavailable. Please make sure you are online and try again.",
            isError: true,
            recommendations: [],
        });
        conversationState.lastIntent = null;
    } finally {
        setLoadingState(false);
        input.value = "";
        renderChatHistory();
        renderActiveFilters();
        // Scroll to latest message
        const chatContainer = document.getElementById("chat-container");
        if (chatContainer) chatContainer.scrollTop = chatContainer.scrollHeight;
    }
}

function buildAssistantMessage(data, isFollowUp) {
    if (data.recommendations.length === 0) {
        return "No matching resources were found for your query. Try rephrasing, selecting a different category, or removing some filters.";
    }
    const count = data.recommendations.length;
    const intentLabel = formatIntent(data.intent);
    if (isFollowUp) {
        return "Here are " + count + " updated result" + (count !== 1 ? "s" : "") + " based on your refinement:";
    }
    return "Here are " + count + " support resource" + (count !== 1 ? "s" : "") + " for " + intentLabel + ":";
}

// ── Chat history rendering ────────────────────────────────────────────────────
function renderChatHistory() {
    resultsSection.replaceChildren();

    const turns = conversationState.turns;
    if (turns.length === 0) return;

    // Chat container
    const chat = document.createElement("div");
    chat.id = "chat-container";
    chat.className = "chat-container";

    turns.forEach(function (turn, index) {
        if (turn.role === "user") {
            chat.appendChild(buildUserBubble(turn, index));
        } else {
            chat.appendChild(buildAssistantBubble(turn, index));
        }
    });

    resultsSection.appendChild(chat);

    // Action bar below chat
    if (turns.length > 0) {
        resultsSection.appendChild(buildChatActions());
    }
}

function buildUserBubble(turn, index) {
    const wrapper = document.createElement("div");
    wrapper.className = "chat-turn chat-turn--user";

    const bubble = document.createElement("div");
    bubble.className = "chat-bubble chat-bubble--user";
    bubble.textContent = turn.content;
    if (turn.isFollowUp) {
        bubble.classList.add("chat-bubble--followup");
    }
    wrapper.appendChild(bubble);

    // Edit button for user messages
    const editBtn = document.createElement("button");
    editBtn.type = "button";
    editBtn.className = "chat-edit-btn";
    editBtn.setAttribute("aria-label", "Edit this message");
    editBtn.innerHTML = '<span aria-hidden="true">✏️</span> Edit';
    editBtn.addEventListener("click", function () {
        conversationState.editingTurnIndex = index;
        input.value = turn.content;
        input.focus();
        input.setSelectionRange(input.value.length, input.value.length);
        // Visual indicator
        queryCard.classList.add("is-editing");
        const indicator = document.getElementById("edit-indicator") || document.createElement("p");
        indicator.id = "edit-indicator";
        indicator.className = "edit-indicator";
        indicator.textContent = "✏️ Editing previous message — submit to replace results from this point.";
        if (!document.getElementById("edit-indicator")) {
            form.insertBefore(indicator, form.firstChild);
        }
        input.scrollIntoView({ behavior: "smooth", block: "center" });
    });
    wrapper.appendChild(editBtn);

    return wrapper;
}

function buildAssistantBubble(turn) {
    const wrapper = document.createElement("div");
    wrapper.className = "chat-turn chat-turn--assistant";

    const bubble = document.createElement("div");
    bubble.className = "chat-bubble chat-bubble--assistant" + (turn.isError ? " chat-bubble--error" : "");

    const msgPara = document.createElement("p");
    msgPara.className = "chat-bubble__text";
    msgPara.textContent = turn.content;
    bubble.appendChild(msgPara);

    // Intent summary if available
    if (!turn.isError && turn.intent && turn.intent !== "general") {
        const summary = document.createElement("div");
        summary.className = "chat-intent-summary";
        const intentSpan = document.createElement("span");
        intentSpan.className = "chat-intent-tag";
        intentSpan.textContent = formatIntent(turn.intent);
        const scoreSpan = document.createElement("span");
        scoreSpan.className = "chat-score-tag";
        scoreSpan.textContent = "Match: " + Math.round((turn.matchScore || 0) * 100) + "%";
        summary.appendChild(intentSpan);
        summary.appendChild(scoreSpan);
        bubble.appendChild(summary);
    }

    wrapper.appendChild(bubble);

    // Recommendation cards for this turn
    if (!turn.isError && turn.recommendations && turn.recommendations.length > 0) {
        const cardsWrapper = document.createElement("div");
        cardsWrapper.className = "chat-cards";
        turn.recommendations.forEach(function (resource) {
            cardsWrapper.appendChild(buildResourceCard(resource));
        });
        wrapper.appendChild(cardsWrapper);
    } else if (!turn.isError && turn.recommendations && turn.recommendations.length === 0) {
        const empty = document.createElement("div");
        empty.className = "result-card result-card--empty";
        const msg = document.createElement("p");
        msg.textContent = "No matching support resources were found. Try rephrasing or selecting a different category.";
        empty.appendChild(msg);
        wrapper.appendChild(empty);
    }

    return wrapper;
}

function buildChatActions() {
    const bar = document.createElement("div");
    bar.className = "chat-actions-bar";

    // Follow-up hint
    const hint = document.createElement("p");
    hint.className = "chat-followup-hint";
    hint.textContent = "You can refine your search (e.g. \"only remote\", \"I am a fresher\") or start a new search below.";
    bar.appendChild(hint);

    const buttons = document.createElement("div");
    buttons.className = "chat-action-buttons";

    const newChat = document.createElement("button");
    newChat.type = "button";
    newChat.className = "start-again-button";
    newChat.textContent = "✦ New Chat";
    newChat.addEventListener("click", function () {
        resetConversation();
        document.getElementById("explore").scrollIntoView({ behavior: "smooth", block: "start" });
    });

    const changeDomain = document.createElement("button");
    changeDomain.type = "button";
    changeDomain.className = "start-again-button start-again-button--secondary";
    changeDomain.textContent = "Change Category";
    changeDomain.addEventListener("click", function () {
        conversationState.selectedCategory = null;
        conversationState.selectedAnswers = {};
        conversationState.accumulatedFilters = {};
        categoryButtons.forEach(function (b) { b.classList.remove("is-selected"); b.setAttribute("aria-pressed", "false"); });
        document.getElementById("explore").scrollIntoView({ behavior: "smooth", block: "start" });
    });

    buttons.appendChild(newChat);
    buttons.appendChild(changeDomain);
    bar.appendChild(buttons);
    return bar;
}

// ── Resource card builder ─────────────────────────────────────────────────────
// Category → default action label (fallback when action_label not in DB)
const CATEGORY_ACTION_LABELS = {
    "Government Schemes":        "Check Eligibility",
    "Internships":               "Apply for Internship",
    "Employment":                "Apply Now",
    "Education":                 "Apply / Enrol",
    "Healthcare":                "Find Service",
    "Legal Support":             "Get Legal Assistance",
    "Emergency":                 "Contact Helpline",
    "Shelters":                  "Contact Shelter",
    "Counselling":               "Book Counselling",
    "Financial Support":         "Apply for Programme",
    "Domestic Violence Support": "Contact Support",
};

function getActionLabel(resource) {
    if (resource.action_label) return resource.action_label;
    return CATEGORY_ACTION_LABELS[resource.category] || "Get Support";
}

function isSafeUrl(url) {
    if (!url || typeof url !== "string") return false;
    const trimmed = url.trim().toLowerCase();
    return trimmed.startsWith("https://") || trimmed.startsWith("http://");
}

function buildResourceCard(resource) {
    const card = document.createElement("div");
    card.className = "result-card resource-card";

    // Name
    const name = document.createElement("h3");
    name.className = "resource-card__name";
    name.textContent = resource.name || "Unnamed Resource";
    card.appendChild(name);

    // Category + location row
    const metaRow = document.createElement("div");
    metaRow.className = "resource-card__meta";
    const badge = document.createElement("span");
    badge.className = "resource-card__badge";
    badge.textContent = resource.category || "";
    metaRow.appendChild(badge);
    if (resource.location) {
        const loc = document.createElement("span");
        loc.className = "resource-card__location";
        loc.textContent = "📍 " + resource.location;
        metaRow.appendChild(loc);
    }
    card.appendChild(metaRow);

    // Match score
    if (resource.score != null) {
        const score = document.createElement("span");
        score.className = "resource-card__score";
        score.textContent = "Match " + Math.round(resource.score * 100) + "%";
        card.appendChild(score);
    }

    // Description
    if (resource.description) {
        const desc = document.createElement("p");
        desc.className = "resource-card__description";
        desc.textContent = resource.description;
        card.appendChild(desc);
    }

    // Why it matches
    if (resource.reason) {
        const reason = document.createElement("p");
        reason.className = "resource-card__reason";
        reason.textContent = resource.reason;
        card.appendChild(reason);
    }

    // ── Action buttons row ────────────────────────────────────────────────────
    // Layout: [Official Website]   [Apply Now / Register / Get Support]
    const actions = document.createElement("div");
    actions.className = "resource-card__actions";

    // A. Official Website button
    const websiteUrl = resource.url || (resource.contact && isSafeUrl(resource.contact) ? resource.contact : null);
    if (websiteUrl && isSafeUrl(websiteUrl)) {
        const webBtn = document.createElement("a");
        webBtn.className = "resource-card__action resource-card__action--website";
        webBtn.href = websiteUrl;
        webBtn.target = "_blank";
        webBtn.rel = "noopener noreferrer";
        webBtn.setAttribute("aria-label", "Official website for " + (resource.name || "this resource") + " (opens in new tab)");
        webBtn.innerHTML = '<span aria-hidden="true">🌐</span> Official Website';
        actions.appendChild(webBtn);
    }

    // B. Apply / Register / Get Support button
    if (resource.apply_url && isSafeUrl(resource.apply_url)) {
        // Only show if apply_url is different from the website URL
        const applyBtn = document.createElement("a");
        applyBtn.className = "resource-card__action resource-card__action--apply";
        applyBtn.href = resource.apply_url;
        applyBtn.target = "_blank";
        applyBtn.rel = "noopener noreferrer";
        const label = getActionLabel(resource);
        applyBtn.setAttribute("aria-label", label + " for " + (resource.name || "this resource") + " (opens in new tab)");
        applyBtn.innerHTML = '<span aria-hidden="true">✅</span> ' + label;
        actions.appendChild(applyBtn);
    } else if (!websiteUrl && resource.contact) {
        // No URL at all — show contact action
        actions.appendChild(buildContactAction(resource.contact, resource.name));
    }

    // C. If only website available and no apply_url, show fallback contact action for phones
    if (actions.children.length > 0 && resource.contact && !isSafeUrl(resource.contact)) {
        actions.appendChild(buildContactAction(resource.contact, resource.name));
    }

    if (actions.children.length > 0) card.appendChild(actions);

    // Source type indicator
    if (resource.source_type) {
        const sourceTag = document.createElement("span");
        sourceTag.className = "resource-card__source-tag resource-card__source-tag--" + resource.source_type;
        sourceTag.textContent = resource.source_type === "database" ? "Verified database record" : resource.source_type;
        card.appendChild(sourceTag);
    }

    return card;
}

function buildContactAction(contact, resourceName) {
    const action = document.createElement("a");
    action.className = "resource-card__action resource-card__action--contact";
    const trimmed = (contact || "").trim();
    const label = /^[+\d][\d\s().,-]{1,}$/.test(trimmed) ? "📞 Call Now" : "📧 Contact";
    action.innerHTML = label;
    action.setAttribute("aria-label", (label.replace(/[^a-zA-Z ]/g, "").trim()) + " " + (resourceName || "resource"));
    if (/^https?:\/\//i.test(trimmed)) {
        action.href = trimmed; action.target = "_blank"; action.rel = "noopener noreferrer";
    } else if (/^[+\d][\d\s().,-]{2,}$/.test(trimmed)) {
        action.href = "tel:" + trimmed.replace(/[^+\d]/g, "");
    } else if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed)) {
        action.href = "mailto:" + trimmed;
    } else {
        action.removeAttribute("href");
        action.setAttribute("aria-disabled", "true");
        action.classList.add("resource-card__action--text");
    }
    return action;
}

function buildDetailRow(icon, text) {
    const row = document.createElement("p");
    row.className = "resource-card__detail";
    const iconSpan = document.createElement("span");
    iconSpan.setAttribute("aria-hidden", "true");
    iconSpan.textContent = icon + " ";
    row.appendChild(iconSpan);
    row.appendChild(document.createTextNode(text));
    return row;
}

// ── UI helpers ────────────────────────────────────────────────────────────────
function setLoadingState(isLoading) {
    loadingMsg.hidden = !isLoading;
    submitBtn.disabled = isLoading;
    submitBtn.setAttribute("aria-label", isLoading ? "Finding support, please wait" : "Find My Support");
    submitBtn.textContent = "";
    if (isLoading) {
        const spinner = document.createElement("span");
        spinner.className = "button-spinner";
        spinner.setAttribute("aria-hidden", "true");
        submitBtn.appendChild(spinner);
        submitBtn.appendChild(document.createTextNode(" Finding support..."));
    } else {
        const icon = document.createElement("span");
        icon.setAttribute("aria-hidden", "true");
        icon.textContent = "\u2728";
        submitBtn.appendChild(icon);
        submitBtn.appendChild(document.createTextNode(" Find My Support"));
    }
    resultsSection.setAttribute("aria-busy", isLoading ? "true" : "false");
}

function showValidationError(message) {
    validationMsg.textContent = message;
    input.style.borderColor = "#c62828";
}

function clearValidationError() {
    validationMsg.textContent = "";
    input.style.borderColor = "";
    // Clear edit indicator if present
    const indicator = document.getElementById("edit-indicator");
    if (indicator && conversationState.editingTurnIndex === null) {
        indicator.remove();
        queryCard.classList.remove("is-editing");
    }
}

function formatIntent(intent) {
    return (intent || "").split("_").map(function (w) { return w.charAt(0).toUpperCase() + w.slice(1); }).join(" ");
}

// ── Initial render ────────────────────────────────────────────────────────────
conversationState.selectedLanguage = languageSelector.value || "en";
renderChatHistory();
