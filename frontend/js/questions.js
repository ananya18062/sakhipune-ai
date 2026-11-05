// questions.js — Domain question flows and helpers for SakhiPune AI
//
// Questions are grounded in the actual 46-resource database.
// Every question has a "Skip" option — no user is forced to disclose.
// Answers are passed to the backend as preference hints, not hard filters,
// except for fields that map directly to supported DB columns
// (work_mode, experience_level, employment_type).

// ── Question definitions ──────────────────────────────────────────────────────
// Each question has:
//   id      — key used in preferences dict sent to backend
//   label   — question text
//   options — chip options shown to user (last option is always Skip)
//   hint    — optional short note shown below the question
//   filterKey — if set, maps to a backend filter field (typed filter, not just preference)

const CATEGORY_QUESTIONS = {
    jobs: [
        {
            id: "job_type",
            label: "What kind of job are you looking for?",
            hint: "Only government employment and skill-based jobs are in the current database.",
            options: ["Full-time", "Part-time / Flexible", "Self-employment", "Government job", "Skill development", "Skip"],
        },
        {
            id: "experience_level",
            label: "What is your experience level?",
            options: ["Fresher / Student", "Some experience (1–2 years)", "Experienced (3+ years)", "Any level", "Prefer not to say"],
            filterKey: "experience_filter",
            filterMap: {
                "Fresher / Student": "fresher",
                "Some experience (1–2 years)": "1_2_years",
                "Experienced (3+ years)": "3_5_years",
                "Any level": "any",
            },
        },
        {
            id: "work_preference",
            label: "Do you prefer remote, hybrid or on-site work?",
            hint: "Most current resources are on-site. Remote options are limited.",
            options: ["On-site", "Remote", "Hybrid", "Open to any", "Skip"],
            filterKey: "work_mode_filter",
            filterMap: {
                "On-site": "on_site",
                "Remote": "remote",
                "Hybrid": "hybrid",
            },
        },
    ],
    internships: [
        {
            id: "interest_area",
            label: "Which field are you interested in?",
            hint: "Current resources cover technical (IT/engineering) and government training schemes.",
            options: ["Technology / IT / Engineering", "Government training scheme", "Business or management", "Social impact", "Any field", "Skip"],
        },
        {
            id: "experience_level",
            label: "Are you a fresher or do you have prior experience?",
            options: ["Fresher / Student", "Some experience", "Experienced", "Skip"],
            filterKey: "experience_filter",
            filterMap: {
                "Fresher / Student": "fresher",
                "Some experience": "1_2_years",
                "Experienced": "3_5_years",
            },
        },
        {
            id: "work_type",
            label: "Do you prefer on-site, remote or hybrid?",
            hint: "Current internship resources are on-site only. No remote internships are in the database.",
            options: ["On-site", "Remote (not currently available)", "Open to any", "Skip"],
            filterKey: "work_mode_filter",
            filterMap: {
                "On-site": "on_site",
            },
        },
    ],
    education: [
        {
            id: "support_type",
            label: "What kind of education support do you need?",
            hint: "The database has scholarships, free school education and university services.",
            options: ["Scholarship", "Free education scheme", "University / college support", "Skill development / vocational", "Study abroad", "Skip"],
        },
        {
            id: "education_level",
            label: "Which level of education are you at?",
            options: ["School (up to Class 12)", "College / undergraduate", "Postgraduate / PhD", "Vocational / diploma", "Skip"],
        },
        {
            id: "scheme_type",
            label: "Are you looking for government or private support?",
            options: ["Government scheme", "University programme", "Any", "Skip"],
        },
    ],
    legal: [
        {
            id: "assistance_type",
            label: "What type of legal help do you need?",
            hint: "Free legal aid, domestic violence protection and court support are available.",
            options: ["Free legal aid", "Domestic violence / protection order", "Court assistance / appeal", "Legal information only", "Skip"],
        },
        {
            id: "urgency",
            label: "How urgent is your situation?",
            hint: "For immediate danger, call 100 (Police) or 112 (Emergency) first.",
            options: ["Immediate — I need help now", "Within a few days", "Not urgent — exploring options", "Skip"],
        },
    ],
    healthcare: [
        {
            id: "support_type",
            label: "What kind of healthcare are you looking for?",
            hint: "Government hospitals, maternity schemes and health centres are available.",
            options: ["Hospital or OPD", "Maternity / pregnancy support", "Government health scheme", "General health service", "Skip"],
        },
        {
            id: "urgency",
            label: "How urgent is your need?",
            options: ["Emergency / urgent", "Soon", "Routine / planned", "Information only", "Skip"],
        },
    ],
    counselling: [
        {
            id: "support_type",
            label: "What kind of support are you looking for?",
            hint: "Free telephone and email counselling helplines are available.",
            options: ["Mental health helpline", "Crisis counselling", "Marathi-language support", "Email counselling", "In-person support", "Skip"],
        },
        {
            id: "format",
            label: "What format would you prefer?",
            options: ["Phone / helpline", "Email", "In person", "Open to any", "Skip"],
        },
    ],
    safety: [
        {
            id: "urgency",
            label: "How urgent is your situation?",
            hint: "If you are in immediate danger, call 100 or 112 right now.",
            options: ["I need help right now", "Today", "Within a few days", "I am looking for information", "Skip"],
        },
        {
            id: "support_type",
            label: "What kind of safety support do you need?",
            options: ["Police helpline", "Women helpline", "Ambulance / medical emergency", "General safety information", "Skip"],
        },
    ],
    financial_support: [
        {
            id: "assistance_type",
            label: "What kind of financial support do you need?",
            hint: "Micro-credit, SHG loans, bank accounts and monthly schemes are available.",
            options: ["Loan or micro-credit", "Monthly financial benefit", "Bank account / savings", "Self-help group", "General guidance", "Skip"],
        },
        {
            id: "scheme_type",
            label: "Are you looking for government or other support?",
            options: ["Government scheme", "Bank / financial institution", "NGO / community", "Any", "Skip"],
        },
    ],
    shelter: [
        {
            id: "requirement",
            label: "What kind of shelter support do you need?",
            hint: "Government shelter homes and emergency OSC referrals are available.",
            options: ["Emergency shelter (tonight)", "Short-term shelter", "Government shelter home", "Safe referral service", "Skip"],
        },
        {
            id: "urgency",
            label: "How soon do you need shelter?",
            options: ["Right now", "Today", "Within a few days", "Exploring options", "Skip"],
        },
    ],
    government_scheme: [
        {
            id: "scheme_type",
            label: "What kind of government scheme are you looking for?",
            hint: "Available: maternity benefits, financial aid, LPG scheme, shelter scheme, rehabilitation.",
            options: ["Maternity / pregnancy benefit", "Monthly financial assistance", "Shelter and rehabilitation", "LPG / household scheme", "Any government scheme", "Skip"],
        },
        {
            id: "eligibility_help",
            label: "What would you like help with?",
            options: ["Finding a suitable scheme", "Checking eligibility", "Understanding how to apply", "General information", "Skip"],
        },
    ],
    entrepreneurship: [
        {
            id: "support_type",
            label: "What kind of support are you looking for?",
            hint: "SHG programmes, micro-credit and livelihood training are available.",
            options: ["Micro-credit or loan", "Self-help group (SHG)", "Livelihood training", "Government scheme", "Skip"],
        },
        {
            id: "business_type",
            label: "What kind of business are you interested in?",
            options: ["Home-based", "Small retail or trade", "Skill or service based", "Any", "Skip"],
        },
    ],
};

// ── Answer → backend filter value mapping ─────────────────────────────────────
// Used by app.js to convert selected option labels into backend filter keys.
function getFilterFromAnswer(categoryKey, questionId, answerLabel) {
    const questions = CATEGORY_QUESTIONS[categoryKey] || [];
    const question = questions.find(function (q) { return q.id === questionId; });
    if (!question || !question.filterKey || !question.filterMap) return null;
    const filterValue = question.filterMap[answerLabel];
    if (!filterValue) return null;
    return { key: question.filterKey, value: filterValue };
}

// ── Category display metadata ─────────────────────────────────────────────────
function getCategoryKey(category) {
    const n = String(category || "")
        .toLowerCase()
        .replace(/&/g, "and")
        .replace(/[^a-z0-9]+/g, "_")
        .replace(/^_|_$/g, "");

    const aliases = {
        education_and_scholarships: "education",
        legal_help: "legal",
        legal_assistance: "legal",
        safety_and_emergency: "safety",
        safety_emergency: "safety",
        government_schemes: "government_scheme",
        financial_support: "financial_support",
        counselling_and_wellbeing: "counselling",
        shelter_and_accommodation: "shelter",
        entrepreneurship_and_self_employment: "entrepreneurship",
        entrepreneurship: "entrepreneurship",
        jobs_and_internships: "jobs",
    };

    return aliases[n] || n;
}

function getQuestionsForCategory(category) {
    return CATEGORY_QUESTIONS[getCategoryKey(category)] || [];
}

const CATEGORY_ICONS = {
    jobs: "\u{1F4BC}",
    internships: "\u{1F4BB}",
    education: "\u{1F393}",
    legal: "\u2696\uFE0F",
    healthcare: "\u2695\uFE0F",
    counselling: "\u{1F4AC}",
    safety: "\u{1F6A8}",
    financial_support: "\u20B9",
    shelter: "\u{1F3E0}",
    government_scheme: "\u{1F3DB}\uFE0F",
    entrepreneurship: "\u{1F331}",
};

// ── Question renderer ─────────────────────────────────────────────────────────
function renderQuestions(category, container) {
    const questions = getQuestionsForCategory(category);
    const categoryKey = getCategoryKey(category);
    let currentIndex = 0;
    const savedAnswers = {};
    container.replaceChildren();

    const form = document.createElement("form");
    form.id = "adaptive-question-form";
    form.noValidate = true;
    form.answerState = savedAnswers;

    // Category heading
    const categoryHeading = document.createElement("div");
    categoryHeading.className = "question-category-heading";
    const categoryIcon = document.createElement("span");
    categoryIcon.className = "question-category-icon";
    categoryIcon.setAttribute("aria-hidden", "true");
    categoryIcon.textContent = CATEGORY_ICONS[categoryKey] || "\u2728";
    const categoryName = document.createElement("strong");
    categoryName.textContent = category;
    categoryHeading.appendChild(categoryIcon);
    categoryHeading.appendChild(categoryName);
    form.appendChild(categoryHeading);

    const intro = document.createElement("p");
    intro.className = "questions-intro";
    intro.textContent = "A few quick questions help us find more relevant results. All questions are optional.";
    form.appendChild(intro);

    // Progress bar
    const progress = document.createElement("div");
    progress.className = "question-progress";
    const progressText = document.createElement("span");
    const progressTrack = document.createElement("span");
    progressTrack.className = "question-progress-track";
    const progressBar = document.createElement("span");
    progressBar.className = "question-progress-bar";
    progressTrack.appendChild(progressBar);
    progress.appendChild(progressText);
    progress.appendChild(progressTrack);
    form.appendChild(progress);

    const questionArea = document.createElement("div");
    questionArea.className = "question-area";
    form.appendChild(questionArea);

    const error = document.createElement("p");
    error.className = "question-validation";
    error.setAttribute("aria-live", "polite");
    form.appendChild(error);

    const navigation = document.createElement("div");
    navigation.className = "question-navigation";
    const back = document.createElement("button");
    back.type = "button";
    back.className = "question-back";
    back.textContent = "\u2190 Back";
    const next = document.createElement("button");
    next.type = "submit";
    next.className = "questions-submit";
    navigation.appendChild(back);
    navigation.appendChild(next);
    form.appendChild(navigation);

    function saveCurrentAnswer() {
        const selected = questionArea.querySelector("input:checked");
        if (selected) {
            const value = selected.value;
            if (value === "Skip") {
                delete savedAnswers[questions[currentIndex].id];
            } else {
                savedAnswers[questions[currentIndex].id] = value;
            }
        }
    }

    function renderCurrentQuestion() {
        const question = questions[currentIndex];
        questionArea.replaceChildren();
        progressText.textContent = "Question " + (currentIndex + 1) + " of " + questions.length;
        progressBar.style.width = ((currentIndex + 1) / questions.length) * 100 + "%";
        next.textContent = currentIndex === questions.length - 1 ? "Show Results \u2192" : "Continue \u2192";
        error.textContent = "";

        const fieldset = document.createElement("fieldset");
        fieldset.className = "question-fieldset";

        const legend = document.createElement("legend");
        legend.textContent = question.label;
        fieldset.appendChild(legend);

        // Optional hint
        if (question.hint) {
            const hint = document.createElement("p");
            hint.className = "question-hint";
            hint.textContent = question.hint;
            fieldset.appendChild(hint);
        }

        const optionList = document.createElement("div");
        optionList.className = "question-options";

        question.options.forEach(function (option, optionIndex) {
            const optionId = question.id + "-" + optionIndex;
            const label = document.createElement("label");
            label.className = "question-option" + (option === "Skip" ? " question-option--skip" : "");

            const input = document.createElement("input");
            input.type = "radio";
            input.name = question.id;
            input.value = option;
            input.id = optionId;
            // Skip is not required — user can always skip
            if (savedAnswers[question.id] === option) {
                input.checked = true;
            }

            const text = document.createElement("span");
            text.textContent = option;

            label.appendChild(input);
            label.appendChild(text);
            optionList.appendChild(label);
        });

        fieldset.appendChild(optionList);
        questionArea.appendChild(fieldset);
        back.disabled = currentIndex === 0;
    }

    form.addEventListener("submit", function (event) {
        event.preventDefault();
        saveCurrentAnswer();

        // Allow proceeding even without an answer (all questions are optional)
        if (currentIndex === questions.length - 1) {
            form.dispatchEvent(new CustomEvent("questions-complete", {
                detail: { answers: collectAnswers(form), categoryKey: categoryKey }
            }));
            return;
        }

        currentIndex += 1;
        renderCurrentQuestion();
    });

    back.addEventListener("click", function () {
        saveCurrentAnswer();
        if (currentIndex === 0) {
            form.dispatchEvent(new CustomEvent("questions-back"));
            return;
        }
        currentIndex -= 1;
        renderCurrentQuestion();
    });

    renderCurrentQuestion();
    container.appendChild(form);
    container.hidden = false;
    return form;
}

function collectAnswers(form) {
    const answers = Object.assign({}, form.answerState || {});
    new FormData(form).forEach(function (value, key) {
        if (key !== "" && value !== "Skip") {
            answers[key] = value;
        }
    });
    return answers;
}

// All questions are now optional — validateAnswers always returns true.
// The function is kept for compatibility with existing callers.
function validateAnswers(questions, answers) {
    return true;
}
