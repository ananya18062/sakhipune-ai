// questions.js - Frontend question definitions and reusable question helpers

const CATEGORY_QUESTIONS = {
    jobs: [
        { id: "job_type", label: "What kind of job are you looking for?", options: ["Full-time", "Part-time", "Work from home", "Any job type", "Other"] },
        { id: "experience_level", label: "What is your experience level?", options: ["Student or fresher", "Some experience", "Experienced", "Prefer not to say"] },
        { id: "work_preference", label: "What work preference suits you?", options: ["Flexible hours", "Fixed hours", "Near my area", "Open to options"] },
    ],
    internships: [
        { id: "interest_area", label: "Which field interests you?", options: ["Technology", "Business", "Design or media", "Social impact", "Other"] },
        { id: "experience_level", label: "What is your experience level?", options: ["Beginner", "Some experience", "Experienced", "Prefer not to say"] },
        { id: "work_type", label: "What type of internship do you prefer?", options: ["On-site", "Remote", "Hybrid", "Open to options"] },
    ],
    education: [
        { id: "support_type", label: "What kind of education support do you need?", options: ["Scholarship", "Admission guidance", "Skill development", "Course information", "Other"] },
        { id: "education_level", label: "What education level are you exploring?", options: ["School", "College", "Vocational training", "Higher studies"] },
        { id: "next_step", label: "What would help you most right now?", options: ["Finding opportunities", "Understanding eligibility", "Applying for support", "Exploring options"] },
    ],
    legal: [
        { id: "assistance_type", label: "What type of legal help do you need?", options: ["Legal information", "Advice", "Help finding a lawyer", "Other"] },
        { id: "urgency", label: "How soon do you need support?", options: ["Immediately", "Within a few days", "Within a few weeks", "General guidance"] },
    ],
    healthcare: [
        { id: "support_type", label: "What kind of healthcare support are you looking for?", options: ["General healthcare", "Women\u2019s health", "Mental wellness", "Finding a nearby service", "Other"] },
        { id: "urgency", label: "How urgent is your need?", options: ["Urgent", "Soon", "Routine support", "Information only"] },
    ],
    counselling: [
        { id: "support_type", label: "What kind of support would feel useful?", options: ["Someone to talk to", "Stress support", "Family or relationship support", "Professional counselling", "Other"] },
        { id: "format", label: "What format would you prefer?", options: ["In person", "Online", "Phone support", "Open to options"] },
    ],
    safety: [
        { id: "urgency", label: "How urgent is your situation?", options: ["I need help right now", "Today", "Soon", "I am looking for information"] },
        { id: "danger", label: "Are you in immediate danger?", options: ["Yes", "No", "I am not sure", "Prefer not to say"] },
    ],
    financial_support: [
        { id: "assistance_type", label: "What kind of financial support do you need?", options: ["Financial guidance", "Emergency assistance", "Education support", "Employment support", "Other"] },
        { id: "next_step", label: "What would help you most?", options: ["Finding an eligible scheme", "Understanding an application", "Finding local support", "General information"] },
    ],
    shelter: [
        { id: "requirement", label: "What shelter support are you looking for?", options: ["Emergency shelter", "Short-term shelter", "Longer-term housing", "Finding a safe place", "Other"] },
        { id: "urgency", label: "How soon do you need shelter support?", options: ["Right now", "Today", "Within a few days", "I am exploring options"] },
    ],
    government_scheme: [
        { id: "scheme_type", label: "What type of scheme or support are you looking for?", options: ["Women\u2019s support", "Education", "Employment", "Financial assistance", "Other"] },
        { id: "eligibility_help", label: "What would you like help with?", options: ["Finding a suitable scheme", "Checking eligibility", "Understanding how to apply", "General information"] },
    ],
};

function getCategoryKey(category) {
    const normalizedCategory = String(category || "")
        .toLowerCase()
        .replace(/&/g, "and")
        .replace(/[^a-z0-9]+/g, "_")
        .replace(/^_|_$/g, "");

    const aliases = {
        education_and_scholarships: "education",
        legal_help: "legal",
        safety_and_emergency: "safety",
        government_schemes: "government_scheme",
        financial_support: "financial_support",
    };

    return aliases[normalizedCategory] || normalizedCategory;
}

function getQuestionsForCategory(category) {
    return CATEGORY_QUESTIONS[getCategoryKey(category)] || [];
}

const CATEGORY_ICONS = {
    jobs: "\u{1F4BC}",
    internships: "\u{1F4BB}",
    education: "\u{1F393}",
    legal: "\u2696",
    healthcare: "\u2695",
    counselling: "\u{1F4AC}",
    safety: "\u{1F6A8}",
    financial_support: "\u20B9",
    shelter: "\u{1F3E0}",
    government_scheme: "\u{1F3DB}",
};

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
    intro.textContent = "Answer a few simple questions so we can understand what may be useful.";
    form.appendChild(intro);

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
            savedAnswers[questions[currentIndex].id] = selected.value;
        }
    }

    function renderCurrentQuestion() {
        const question = questions[currentIndex];
        questionArea.replaceChildren();
        progressText.textContent = "Step " + (currentIndex + 1) + " of " + questions.length;
        progressBar.style.width = ((currentIndex + 1) / questions.length) * 100 + "%";
        next.textContent = currentIndex === questions.length - 1 ? "Continue \u2192" : "Continue \u2192";
        error.textContent = "";

        const fieldset = document.createElement("fieldset");
        fieldset.className = "question-fieldset";

        const legend = document.createElement("legend");
        legend.textContent = question.label;
        fieldset.appendChild(legend);

        const optionList = document.createElement("div");
        optionList.className = "question-options";

        question.options.forEach(function (option, optionIndex) {
            const optionId = question.id + "-" + optionIndex;
            const label = document.createElement("label");
            label.className = "question-option";

            const input = document.createElement("input");
            input.type = "radio";
            input.name = question.id;
            input.value = option;
            input.id = optionId;
            input.required = true;
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
        if (!savedAnswers[questions[currentIndex].id]) {
            error.textContent = "Please complete the required questions.";
            return;
        }

        if (currentIndex === questions.length - 1) {
            form.dispatchEvent(new CustomEvent("questions-complete", { detail: { answers: collectAnswers(form) } }));
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
        if (key !== "") {
            answers[key] = value;
        }
    });
    return answers;
}

function validateAnswers(questions, answers) {
    return questions.every(function (question) {
        return Boolean(answers[question.id]);
    });
}
