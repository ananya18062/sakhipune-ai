# nlp_service.py — NLP preprocessing + intent classification
#
# Preprocessing pipeline:
#   raw text → lowercase → tokenize → remove stop words
#            → remove punctuation → lemmatize → clean text
#
# Intent classification:
#   preprocessed tokens → keyword matching → intent + confidence score

import spacy

# Load the English model once at module level.
# This avoids reloading the model on every function call.
nlp = spacy.load("en_core_web_sm")


# ── Intent keyword map ────────────────────────────────────────────────────────
# Each intent maps to a list of keywords (already lemmatized / base form).
# Add or edit keywords here to tune classification — no code logic changes needed.
#
# Keyword weight:
#   Each matched keyword contributes equally.
#   confidence = matched_keywords / total_keywords_for_intent  (capped at 1.0)
#   A minimum of 1 match is required to classify as that intent.

INTENT_KEYWORDS: dict[str, list[str]] = {
    "emergency": [
        "emergency", "urgent", "police", "danger", "attack",
        "threat", "assault", "kidnap", "missing", "sos", "crisis", "immediate",
        "unsafe", "afraid", "scare", "scared", "violence", "harm",
    ],
    "legal": [
        "legal", "lawyer", "law", "court", "justice", "fir", "complaint",
        "right", "case", "advocate", "police", "bail", "divorce", "harassment",
        "maintenance", "alimony", "property", "custody",
        "assistance", "protection", "aid", "advice", "representation",
    ],
    "healthcare": [
        "health", "healthcare", "hospital", "doctor", "medicine", "medical",
        "clinic", "treatment", "disease", "illness", "pregnancy", "maternal",
        "nutrition", "menstrual", "gynecologist", "nurse", "ambulance",
        "gynaecology", "gynecology", "antenatal", "prenatal", "postnatal",
        "obstetrics", "reproductive", "vaccination", "immunisation",
        "immunization", "wellness", "midwife", "maternity",
    ],
    "counselling": [
        "counsel", "counselling", "therapy", "therapist", "mental",
        "psychologist", "depression", "anxiety", "stress", "trauma",
        "emotional", "listen", "talk", "grief", "fear",
        "depress", "anxious", "worry", "sad", "lonely", "helpless",
        "wellbeing", "wellness", "mindful", "psychological",
    ],
    "domestic_violence": [
        "domestic", "violence", "abuse", "abusive", "husband", "partner",
        "beat", "hit", "assault", "threat", "home", "unsafe", "dowry",
        "harassment", "torture", "escape", "leave",
    ],
    "employment": [
        "job", "employment", "work", "career", "skill", "training",
        "interview", "resume", "salary", "hire", "office", "business",
        "freelance", "vocational", "placement", "income", "earn",
        "internship", "apprenticeship", "stipend",
        "opportunity", "vacancy", "opening", "entry", "recruit",
    ],
    "education": [
        "education", "school", "college", "study", "scholarship",
        "course", "degree", "learn", "university", "admission", "fee",
        "tuition", "literacy", "vocational", "training", "exam",
        "higher", "graduate", "postgraduate", "merit", "stipend",
        "girl", "women", "hostel", "institute", "certificate",
        "grant", "bursary", "apply",
    ],
    "government_scheme": [
        "scheme", "government", "yojana", "subsidy", "benefit",
        "apply", "form", "registration", "pension", "ration",
        "welfare", "programme", "policy", "certificate",
    ],
    "financial_support": [
        "money", "financial", "loan", "fund", "finance", "bank",
        "microfinance", "saving", "credit", "debt", "poverty",
        "economic", "income", "expense", "afford", "fee", "cost",
        "livelihood", "bill", "allowance", "pension", "assistance",
        "welfare", "grant", "subsidy", "stipend", "benefit", "aid",
    ],
    "shelter": [
        "shelter", "home", "house", "safe", "stay", "accommodation",
        "refuge", "place", "live", "escape", "housing", "dormitory",
        "hostel", "ngo", "centre",
    ],
}

# Limited multilingual aliases for common project queries. These are explicit
# vocabulary mappings, not broad Hindi/Marathi language understanding.
MULTILINGUAL_INTENT_KEYWORDS: dict[str, list[str]] = {
    "employment": ["नौकरी", "रोजगार", "काम", "नोकरी", "नियुक्ति"],
    "education":  ["छात्रवृत्ति", "स्कॉलरशिप", "वजीफा", "शिष्यवृत्ती", "शिक्षण", "शिक्षा"],
    "healthcare": ["आरोग्य", "दवाखाना", "रुग्णालय", "डॉक्टर", "आरोग्य सेवा"],
}


# ── Preprocessing functions ───────────────────────────────────────────────────

def get_tokens(text: str) -> list[str]:
    """
    Tokenizes and cleans the input text.

    Steps applied to each token:
      1. Lowercase
      2. Skip stop words  (e.g. "I", "a", "the", "is")
      3. Skip punctuation (e.g. ".", ",", "!", "?")
      4. Skip whitespace-only tokens
      5. Lemmatize        (e.g. "finding" → "find", "jobs" → "job")

    Returns a list of clean lemmatized tokens.
    Returns an empty list for empty or whitespace-only input.

    Example:
        get_tokens("I need help finding a job in Pune!")
        → ["need", "help", "find", "job", "pune"]
    """
    if not isinstance(text, str) or not text.strip():
        return []

    doc = nlp(text.lower())

    tokens = []
    for token in doc:
        if token.is_stop:
            continue
        if token.is_punct:
            continue
        if token.is_space:
            continue
        lemma = token.lemma_.strip().lower()
        if len(lemma) < 2:
            continue
        tokens.append(lemma)

    return tokens


def preprocess_text(text: str) -> str:
    """
    Full NLP preprocessing pipeline.

    Takes raw user input and returns a single cleaned string
    of meaningful lemmatized words separated by spaces.

    Returns an empty string for empty or whitespace-only input.

    Examples:
        preprocess_text("I need help finding a job in Pune.")
        → "need help find job pune"

        preprocess_text("Where can I get free legal advice?")
        → "free legal advice"
    """
    tokens = get_tokens(text)
    return " ".join(tokens)


# ── Intent classification ─────────────────────────────────────────────────────

def classify_intent(text: str) -> dict:
    """
    Classifies the user's message into one of the supported intents
    using keyword matching on preprocessed tokens.

    Confidence is calculated as:
        matched_keywords / total_keywords_for_intent
    Capped at 1.0. This is a rule-based score, not an ML probability.

    Returns:
        {
            "intent":     str,   # e.g. "employment"
            "confidence": float  # 0.0 – 1.0
        }

    Falls back to intent="general" with confidence=0.0
    when no keywords match any category.

    Examples:
        classify_intent("I need a job")
        → {"intent": "employment", "confidence": 0.12}

        classify_intent("I need police help urgently")
        → {"intent": "emergency", "confidence": 0.23}

        classify_intent("hello")
        → {"intent": "general", "confidence": 0.0}
    """
    tokens = get_tokens(text)

    if not tokens:
        return {"intent": "general", "confidence": 0.0}

    token_set = set(tokens)  # use a set for O(1) lookups

    best_intent = "general"
    best_score = 0.0

    for intent, keywords in INTENT_KEYWORDS.items():
        multilingual_keywords = MULTILINGUAL_INTENT_KEYWORDS.get(intent, [])
        matched = token_set.intersection(set(keywords + multilingual_keywords))

        if not matched:
            continue

        # Score = fraction of this intent's keywords that were matched
        score = round(len(matched) / len(keywords), 2)

        if score > best_score:
            best_score = score
            best_intent = intent

    return {"intent": best_intent, "confidence": best_score}
