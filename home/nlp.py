# home/nlp.py
"""
NLP engine for the Review Sentiment & NLP Analysis challenge.

Components:
  LanguageDetector   — detects en / sw / other using lightweight heuristics
                       + langdetect fallback
  SentimentScorer    — hybrid: AfriSenti-aware rules for Swahili,
                       LLM scoring for English, heuristic fallback
  TopicExtractor     — LLM-based topic + key phrase extraction,
                       with TF-IDF keyword fallback
  AspectAnalyser     — scores 8 hospitality aspects per review
  ReviewNLPPipeline  — orchestrates all of the above for one Review

All components are stateless and thread-safe.
All external calls (LLM) are wrapped in try/except and have fallbacks
so the pipeline never crashes on a single review.
"""
from __future__ import annotations
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


# ── Hospitality aspects we care about ─────────────────────────────────────
ASPECTS = [
    "cleanliness",
    "staff",
    "location",
    "value",
    "amenities",
    "wifi",
    "food",
    "noise",
]

# ── Swahili sentiment lexicon (AfriSenti-informed) ────────────────────────
# Positive and negative Swahili/Sheng words relevant to hospitality
SWAHILI_POSITIVE = {
    "nzuri", "vizuri", "bora", "safi", "salama", "furaha", "penda",
    "starehe", "karibu", "asante", "tukufu", "faida", "bure", "rahisi",
    "upole", "msaada", "haraka", "mpya", "sawa", "laini", "starish",
    "kamili", "poa", "freshi", "nice", "good", "great", "excellent",
    "wonderful", "amazing", "perfect", "clean", "friendly", "helpful",
}

SWAHILI_NEGATIVE = {
    "mbaya", "chafu", "tatizo", "shida", "hasira", "vibaya", "polepole",
    "kelele", "uchafu", "dharau", "bei", "ghali", "pungufu", "kasoro",
    "kero", "ugumu", "dirty", "bad", "poor", "noisy", "slow", "expensive",
    "broken", "rude", "awful", "terrible", "horrible", "worst", "filthy",
}

# English sentiment word lists for heuristic fallback
ENGLISH_POSITIVE = {
    "excellent", "amazing", "wonderful", "fantastic", "perfect", "great",
    "good", "clean", "friendly", "helpful", "comfortable", "lovely",
    "beautiful", "nice", "pleasant", "enjoyed", "recommended", "love",
    "best", "outstanding", "superb", "immaculate", "spotless", "cozy",
    "welcoming", "attentive", "efficient", "quiet", "convenient",
}

ENGLISH_NEGATIVE = {
    "dirty", "rude", "noisy", "terrible", "awful", "horrible", "bad",
    "poor", "disappointing", "uncomfortable", "broken", "slow", "cold",
    "smelly", "unfriendly", "expensive", "overpriced", "small", "dark",
    "worn", "outdated", "unclean", "unhelpful", "ignored", "waiting",
    "mold", "cockroach", "bug", "leak", "stain", "smell",
}

# Aspect keyword map
ASPECT_KEYWORDS: dict[str, set[str]] = {
    "cleanliness": {"clean", "dirty", "spotless", "filthy", "immaculate", "safi", "chafu", "mold", "stain", "hygiene"},
    "staff":       {"staff", "service", "friendly", "rude", "helpful", "attentive", "reception", "wafanyakazi", "huduma"},
    "location":    {"location", "central", "far", "close", "walking", "access", "eneo", "mahali", "transport"},
    "value":       {"value", "price", "expensive", "cheap", "worth", "overpriced", "bei", "gharama", "affordable"},
    "amenities":   {"pool", "gym", "spa", "parking", "elevator", "facility", "vifaa", "amenity", "air conditioning"},
    "wifi":        {"wifi", "internet", "connection", "slow", "fast", "signal", "intaneti", "mtandao"},
    "food":        {"food", "breakfast", "restaurant", "meal", "taste", "chakula", "asubuhi", "dinner", "menu"},
    "noise":       {"noise", "quiet", "loud", "party", "street", "kelele", "utulivu", "disturb", "hear"},
}


# ── Language Detector ──────────────────────────────────────────────────────
class LanguageDetector:
    """
    Lightweight language detection.
    Uses word-overlap heuristics first (fast, no dependencies),
    falls back to langdetect if installed.
    """

    # High-frequency Swahili function words
    SWAHILI_MARKERS = {
        "na", "ya", "wa", "ni", "kwa", "la", "za", "ku", "si",
        "hii", "hiyo", "hilo", "katika", "kwamba", "lakini",
        "pia", "sana", "kabla", "baada", "kuwa", "alikuwa",
        "watu", "siku", "muda", "ndani", "nje",
    }

    def detect(self, text: str) -> str:
        """Returns 'sw', 'en', or 'other'."""
        if not text or len(text.strip()) < 5:
            return "en"

        words = set(re.findall(r"\b\w+\b", text.lower()))

        # Count Swahili marker overlap
        sw_hits = len(words & self.SWAHILI_MARKERS)
        if sw_hits >= 3 or (len(words) > 0 and sw_hits / len(words) > 0.15):
            return "sw"

        # Try langdetect if installed
        try:
            from langdetect import detect as ld_detect
            lang = ld_detect(text)
            if lang == "sw":
                return "sw"
            if lang.startswith("en"):
                return "en"
            return "other"
        except Exception:
            pass

        return "en"


language_detector = LanguageDetector()


# ── Sentiment Scorer ───────────────────────────────────────────────────────

class SentimentScorer:
    """
    Hybrid sentiment scorer:
      1. AfriSenti-aware lexicon for Swahili home (fast, offline)
      2. LLM scoring for English (accurate, async)
      3. Heuristic English lexicon as fallback

    Returns (label, score, model_name):
      label: "positive" | "negative" | "neutral"
      score: 0.0–1.0 confidence
      model_name: which method was used
    """

    def score(
        self,
        text: str,
        language: str = "en",
        reviewer_score: Optional[float] = None,
    ) -> tuple[str, float, str]:
        """
        Primary entry point.
        reviewer_score (1–10) is used as a strong signal when available.
        """
        if not text or not text.strip():
            return self._from_reviewer_score(reviewer_score)

        # Swahili: use lexicon (AfriSenti-informed)
        if language == "sw":
            return self._swahili_lexicon(text, reviewer_score)

        # English: try LLM first, fall back to heuristic
        llm_result = self._llm_score(text, language)
        if llm_result:
            label, score = llm_result
            # Blend with reviewer_score if available
            if reviewer_score is not None:
                rs_label, rs_score = self._reviewer_score_signal(reviewer_score)
                if rs_label == label:
                    score = min(1.0, score * 1.1)
            return label, score, "llm"

        return self._heuristic_english(text, reviewer_score)

    def _from_reviewer_score(self, rs: Optional[float]) -> tuple[str, float, str]:
        if rs is None:
            return "neutral", 0.5, "default"
        if rs >= 8.0:
            return "positive", 0.75, "reviewer_score"
        if rs <= 4.0:
            return "negative", 0.75, "reviewer_score"
        return "neutral", 0.5, "reviewer_score"

    def _reviewer_score_signal(self, rs: float) -> tuple[str, float]:
        if rs >= 8.0:
            return "positive", min(1.0, (rs - 7) / 3)
        if rs <= 4.0:
            return "negative", min(1.0, (5 - rs) / 4)
        return "neutral", 0.5

    def _swahili_lexicon(
        self, text: str, reviewer_score: Optional[float]
    ) -> tuple[str, float, str]:
        """
        AfriSenti-informed Swahili sentiment.
        First tries the transformer model, falls back to lexicon.
        Uses combined Swahili + common English words since East African
        home are often code-switched.
        """
        # Try AfriSenti transformer model first
        try:
            label, score, model = afrisenti_analyzer.analyze(text, "sw")
            if model == "afrisenti_transformer":
                # Blend with reviewer_score if available
                if reviewer_score is not None:
                    rs_label, _ = self._reviewer_score_signal(reviewer_score)
                    if rs_label == label:
                        score = min(1.0, score * 1.1)
                return label, round(score, 4), model
        except Exception as e:
            logger.debug(f"AfriSenti transformer failed, falling back to lexicon: {e}")

        # Fallback to lexicon-based approach
        words = set(re.findall(r"\b\w+\b", text.lower()))
        pos = len(words & SWAHILI_POSITIVE)
        neg = len(words & SWAHILI_NEGATIVE)
        total = pos + neg

        if total == 0:
            return self._from_reviewer_score(reviewer_score)

        ratio = pos / total
        if ratio >= 0.65:
            label, score = "positive", min(0.95, 0.55 + ratio * 0.4)
        elif ratio <= 0.35:
            label, score = "negative", min(0.95, 0.55 + (1 - ratio) * 0.4)
        else:
            label, score = "neutral", 0.5

        # Reviewer score override for strong signals
        if reviewer_score is not None:
            if reviewer_score >= 9.0 and label != "negative":
                label, score = "positive", max(score, 0.80)
            elif reviewer_score <= 3.0 and label != "positive":
                label, score = "negative", max(score, 0.80)

        return label, round(score, 4), "afrisenti_lexicon"

    def _llm_score(
        self, text: str, language: str
    ) -> Optional[tuple[str, float]]:
        """Call LLM for sentiment. Returns (label, score) or None."""
        try:
            import json
            from ai.services import ai_service_provider
            from django.contrib.auth import get_user_model
            User = get_user_model()
            system_user = User.objects.filter(is_superuser=True).first()
            if not system_user:
                return None

            prompt = f"""Analyse the sentiment of this hospitality review.
Language hint: {language}
Review: \"\"\"{text[:800]}\"\"\"

Return JSON only — no markdown, no explanation:
{{"label": "positive|negative|neutral", "score": 0.0-1.0, "confidence": "high|medium|low"}}"""

            response = ai_service_provider.chat_completion_sync(
                user=system_user,
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.0,
                max_tokens=80,
                response_format={"type": "json_object"},
                timeout=8,
            )
            if response and response.get("content"):
                data = json.loads(response["content"])
                label = data.get("label", "neutral")
                score = float(data.get("score", 0.5))
                if label not in ("positive", "negative", "neutral"):
                    label = "neutral"
                return label, round(score, 4)
        except Exception as e:
            logger.debug(f"LLM sentiment failed: {e}")
        return None

    def _heuristic_english(
        self, text: str, reviewer_score: Optional[float]
    ) -> tuple[str, float, str]:
        words = set(re.findall(r"\b\w+\b", text.lower()))
        pos = len(words & ENGLISH_POSITIVE)
        neg = len(words & ENGLISH_NEGATIVE)
        total = pos + neg

        if total == 0:
            return self._from_reviewer_score(reviewer_score)

        ratio = pos / total
        if ratio >= 0.60:
            label, score = "positive", min(0.90, 0.50 + ratio * 0.40)
        elif ratio <= 0.40:
            label, score = "negative", min(0.90, 0.50 + (1 - ratio) * 0.40)
        else:
            label, score = "neutral", 0.50

        if reviewer_score is not None:
            rs_label, _ = self._reviewer_score_signal(reviewer_score)
            if rs_label == label:
                score = min(0.95, score * 1.1)

        return label, round(score, 4), "heuristic"


sentiment_scorer = SentimentScorer()


# ── AfriSenti Model-Based Sentiment Analyzer ───────────────────────────────

class AfriSentiAnalyzer:
    """
    Local AfriSenti transformer model for African language sentiment analysis.
    Uses the downloaded model.safetensors file for zero-cost, offline inference.
    Supports multiple African languages including Swahili, Arabic, Amharic, etc.
    """

    def __init__(self, model_path: str = None):
        self.model = None
        self.tokenizer = None
        self.device = "cpu"
        self.model_path = model_path or "model.safetensors"
        self.config_path = "config.json"
        self._initialized = False
        self._init_failed = False

    def _load_model(self):
        """Lazily load the AfriSenti model on first use."""
        if self._initialized or self._init_failed:
            return

        try:
            import os
            if not os.path.exists(self.model_path):
                logger.warning(f"AfriSenti model not found at {self.model_path}")
                self._init_failed = True
                return

            if not os.path.exists(self.config_path):
                logger.warning(f"AfriSenti config not found at {self.config_path}")
                self._init_failed = True
                return

            import json
            import torch
            from transformers import AutoTokenizer, AutoModelForSequenceClassification

            # Load config to get base model name
            with open(self.config_path, 'r') as f:
                config = json.load(f)

            base_model = config.get('base_model_name', 'bert-base-multilingual-uncased')

            # Load tokenizer from HuggingFace (small download, ~1MB)
            self.tokenizer = AutoTokenizer.from_pretrained(base_model)

            # Load model from local safetensors file
            from transformers import AutoConfig
            model_config = AutoConfig.from_pretrained(
                base_model,
                num_labels=3,
                label2id={"negative": 0, "neutral": 1, "positive": 2},
                id2label={0: "negative", 1: "neutral", 2: "positive"},
            )

            self.model = AutoModelForSequenceClassification.from_pretrained(
                base_model,
                state_dict=torch.load(self.model_path, map_location=self.device, weights_only=True),
                config=model_config,
                local_files_only=True,
            )
            self.model.to(self.device)
            self.model.eval()

            self._initialized = True
            logger.info("AfriSenti model loaded successfully")

        except Exception as e:
            logger.warning(f"Failed to load AfriSenti model: {e}")
            self._init_failed = True

    def analyze(self, text: str, language: str = "sw") -> tuple[str, float, str]:
        """
        Analyze sentiment using the local AfriSenti model.
        Returns (label, score, model_name).
        """
        if not text or not text.strip():
            return "neutral", 0.5, "empty"

        self._load_model()

        if not self._initialized:
            return "neutral", 0.5, "model_unavailable"

        try:
            import torch

            # Tokenize
            inputs = self.tokenizer(
                text,
                padding=True,
                truncation=True,
                max_length=128,
                return_tensors="pt",
            ).to(self.device)

            # Inference
            with torch.no_grad():
                outputs = self.model(**inputs)
                probabilities = torch.nn.functional.softmax(outputs.logits, dim=-1)[0]

            # Get prediction
            confidence, predicted = torch.max(probabilities, dim=0)
            label_id = predicted.item()
            score = confidence.item()

            # Map label ID to sentiment
            id2label = self.model.config.id2label
            label = id2label.get(label_id, "neutral")

            return label, round(score, 4), "afrisenti_transformer"

        except Exception as e:
            logger.warning(f"AfriSenti inference failed: {e}")
            return "neutral", 0.5, "inference_error"


# Initialize AfriSenti analyzer (lazy loading)
afrisenti_analyzer = AfriSentiAnalyzer()


# ── Topic Extractor ────────────────────────────────────────────────────────

class TopicExtractor:
    """
    Extracts topics and key phrases from a review.

    Strategy:
      1. LLM: returns structured JSON with topic labels + key phrases.
         Best quality, used when LLM is available.
      2. Keyword fallback: matches text against ASPECT_KEYWORDS.
         Always works, always fast.
    """

    # Canonical topic labels — LLM is prompted to use these
    CANONICAL_TOPICS = [
        "Cleanliness & Hygiene",
        "Staff & Service",
        "Location & Accessibility",
        "Value for Money",
        "Amenities & Facilities",
        "WiFi & Connectivity",
        "Food & Breakfast",
        "Noise & Comfort",
        "Room Quality",
        "Check-in & Check-out",
        "Safety & Security",
        "Local Experience",       # East African context
        "Cultural Hospitality",   # East African context — warmth, Ubuntu
    ]

    def extract(self, text: str, language: str = "en") -> dict:
        """
        Returns:
        {
            "topics": ["Cleanliness & Hygiene", "Staff & Service"],
            "key_phrases": ["very clean rooms", "friendly staff"],
            "aspect_scores": {"cleanliness": 0.9, "staff": 0.8, ...}
        }
        """
        result = {
            "topics":        [],
            "key_phrases":   [],
            "aspect_scores": {},
        }

        if not text or not text.strip():
            return result

        # Try LLM
        llm_result = self._llm_extract(text, language)
        if llm_result:
            result.update(llm_result)
        else:
            # Keyword fallback for topics
            result["topics"] = self._keyword_topics(text)

        # Always run aspect scoring (fast, no LLM needed)
        result["aspect_scores"] = self._aspect_scores(text)

        return result

    def _llm_extract(self, text: str, language: str) -> Optional[dict]:
        try:
            import json
            from ai.services import ai_service_provider
            from django.contrib.auth import get_user_model
            User = get_user_model()
            system_user = User.objects.filter(is_superuser=True).first()
            if not system_user:
                return None

            topics_str = "\n".join(f"- {t}" for t in self.CANONICAL_TOPICS)
            prompt = f"""Extract topics and key phrases from this hospitality review.
Language: {language}
Review: \"\"\"{text[:800]}\"\"\"

Available topics:
{topics_str}

Return JSON only:
{{
  "topics": ["topic1", "topic2"],
  "key_phrases": ["phrase1", "phrase2", "phrase3"]
}}
Only use topics from the list. Include 2-5 key phrases (exact short quotes from the review)."""

            response = ai_service_provider.chat_completion_sync(
                user=system_user,
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.1,
                max_tokens=200,
                response_format={"type": "json_object"},
                timeout=10,
            )
            if response and response.get("content"):
                data = json.loads(response["content"])
                topics = [
                    t for t in data.get("topics", [])
                    if t in self.CANONICAL_TOPICS
                ]
                phrases = data.get("key_phrases", [])[:8]
                return {"topics": topics, "key_phrases": phrases}
        except Exception as e:
            logger.debug(f"LLM topic extraction failed: {e}")
        return None

    def _keyword_topics(self, text: str) -> list[str]:
        """Map text to canonical topics via aspect keywords."""
        text_lower = text.lower()
        words = set(re.findall(r"\b\w+\b", text_lower))
        topic_map = {
            "cleanliness": "Cleanliness & Hygiene",
            "staff":       "Staff & Service",
            "location":    "Location & Accessibility",
            "value":       "Value for Money",
            "amenities":   "Amenities & Facilities",
            "wifi":        "WiFi & Connectivity",
            "food":        "Food & Breakfast",
            "noise":       "Noise & Comfort",
        }
        found = []
        for aspect, topic in topic_map.items():
            if words & ASPECT_KEYWORDS.get(aspect, set()):
                found.append(topic)
        return found

    def _aspect_scores(self, text: str) -> dict[str, float]:
        """
        Score each aspect 0.0–1.0 based on sentiment-weighted keyword presence.
        Positive keywords near the aspect → score > 0.5
        Negative keywords near the aspect → score < 0.5
        Aspect not mentioned → not included in output
        """
        text_lower = text.lower()
        words = set(re.findall(r"\b\w+\b", text_lower))
        scores = {}

        pos_words = SWAHILI_POSITIVE | ENGLISH_POSITIVE
        neg_words = SWAHILI_NEGATIVE | ENGLISH_NEGATIVE

        for aspect, keywords in ASPECT_KEYWORDS.items():
            if not (words & keywords):
                continue

            # Look in a 60-char window around the keyword
            aspect_score = 0.5
            mention_count = 0
            for kw in keywords:
                for match in re.finditer(r"\b" + re.escape(kw) + r"\b", text_lower):
                    start = max(0, match.start() - 60)
                    end   = min(len(text_lower), match.end() + 60)
                    window = text_lower[start:end]
                    window_words = set(re.findall(r"\b\w+\b", window))
                    pos_hits = len(window_words & pos_words)
                    neg_hits = len(window_words & neg_words)
                    if pos_hits + neg_hits > 0:
                        aspect_score += (pos_hits - neg_hits) / (pos_hits + neg_hits) * 0.4
                        mention_count += 1

            if mention_count > 0:
                scores[aspect] = round(max(0.0, min(1.0, aspect_score / mention_count)), 3)

        return scores


topic_extractor = TopicExtractor()


# ── Full pipeline ──────────────────────────────────────────────────────────

class ReviewNLPPipeline:
    """
    Orchestrates LanguageDetector → SentimentScorer → TopicExtractor
    for a single Review instance.

    Usage:
        from home.nlp import review_pipeline
        review_pipeline.process(review_instance)  # saves in-place
    """

    def process(self, review) -> bool:
        """
        Run the full NLP pipeline on a Review instance.
        Updates the instance fields and calls save().
        Returns True on success, False on failure.
        """
        try:
            text = review.display_text
            if not text:
                review.is_processed = True
                review.processing_error = "empty text"
                review.save(update_fields=[
                    "is_processed", "processing_error", "updated_at"
                ])
                return False

            # 1. Language detection
            language = language_detector.detect(text)
            review.language = language

            # 2. Sentiment scoring
            label, score, model_name = sentiment_scorer.score(
                text,
                language=language,
                reviewer_score=review.reviewer_score,
            )
            review.sentiment       = label
            review.sentiment_score = score
            review.sentiment_model = model_name

            # 3. Topic + aspect extraction
            extraction = topic_extractor.extract(text, language=language)
            review.topic_labels  = extraction["topics"]
            review.key_phrases   = extraction["key_phrases"]
            review.aspect_scores = extraction["aspect_scores"]

            # 4. Mark processed
            review.is_processed     = True
            review.processing_error = ""

            review.save(update_fields=[
                "language", "sentiment", "sentiment_score", "sentiment_model",
                "topic_labels", "key_phrases", "aspect_scores",
                "is_processed", "processing_error", "updated_at",
            ])
            return True

        except Exception as e:
            logger.error(f"ReviewNLPPipeline.process failed for {review.pk}: {e}")
            try:
                review.processing_error = str(e)[:500]
                review.is_processed = False
                review.save(update_fields=["processing_error", "updated_at"])
            except Exception:
                pass
            return False

    def process_batch(self, queryset, limit: int = 500) -> dict:
        """
        Process a batch of unprocessed home.
        Returns {"processed": N, "succeeded": N, "failed": N}
        """
        succeeded = failed = 0
        home = queryset.filter(is_processed=False)[:limit]
        for review in home:
            ok = self.process(review)
            if ok:
                succeeded += 1
            else:
                failed += 1
        return {
            "processed":  succeeded + failed,
            "succeeded":  succeeded,
            "failed":     failed,
        }


review_pipeline = ReviewNLPPipeline()


# ── NLP Query Engine for Chat ──────────────────────────────────────────────

class NLPQueryEngine:
    """
    Natural language query engine for the command palette chat.
    Translates user questions into database queries and uses LLM for responses.
    """

    def __init__(self):
        from home.llm_service import LLMService
        self.llm = LLMService()

    def process_query(self, query: str, history: list = None) -> dict:
        """
        Process a natural language query about hotel reviews.
        Supports both English and Swahili queries using LLM for intent detection.
        Returns {"response": str, "data": dict}
        """
        query_lower = query.lower().strip()

        # First, use LLM to detect intent for better Swahili understanding
        try:
            intent = self._detect_intent_with_llm(query)
            if intent:
                return self._execute_intent(intent, query_lower)
        except Exception as e:
            logger.debug(f"LLM intent detection failed, using keyword fallback: {e}")

        # Fallback to keyword-based detection
        return self._detect_intent_by_keywords(query_lower)

    def _detect_intent_with_llm(self, query: str) -> Optional[str]:
        """Use LLM to detect query intent for better multilingual support."""
        try:
            prompt = f"""You are a hotel review analytics assistant. Analyze this query and return ONLY a JSON object with the intent.

Query: "{query}"

Return JSON only (no markdown):
{{"intent": "best" or "worst" or "cleanliness" or "staff" or "location" or "value" or "wifi" or "noise" or "food" or "complaints" or "general"}}

The query may be in English or Swahili. Map to these intents:
- "best" = best/top hotels (Swahili: bora, nzuri, vizuri)
- "worst" = worst/bad hotels (Swahili: mbaya, chafu, vibaya)
- "cleanliness" = cleanliness/hygiene (Swahili: usafi, safi)
- "staff" = staff/service (Swahili: wafanyakazi, huduma)
- "location" = location/area (Swahili: eneo, mahali)
- "value" = value/price (Swahili: bei, gharama)
- "wifi" = wifi/internet (Swahili: intaneti, mtandao)
- "noise" = noise/quiet (Swahili: kelele, utulivu)
- "food" = food/breakfast (Swahili: chakula)
- "complaints" = complaints/negative (Swahili: malalamiko)
- "general" = anything else"""

            from home.llm_service import _llm_service
            result_str = _llm_service._call_with_failover(
                prompt, temperature=0.1, max_tokens=50, json_response=True
            )
            if result_str:
                result = json.loads(result_str)
                return result.get("intent", None)
        except Exception as e:
            logger.debug(f"LLM intent detection error: {e}")
        return None

    def _execute_intent(self, intent: str, query_lower: str) -> dict:
        """Execute a detected intent."""
        intent_handlers = {
            "best": self._get_best_hotels,
            "worst": self._get_worst_hotels,
            "cleanliness": lambda q: self._get_hotels_by_aspect("cleanliness", q),
            "staff": lambda q: self._get_hotels_by_aspect("staff", q),
            "location": lambda q: self._get_hotels_by_aspect("location", q),
            "value": lambda q: self._get_hotels_by_aspect("value", q),
            "wifi": lambda q: self._get_hotels_by_aspect("wifi", q),
            "noise": lambda q: self._get_hotels_by_aspect("noise", q),
            "food": lambda q: self._get_hotels_by_aspect("food", q),
            "complaints": self._get_common_complaints,
        }

        handler = intent_handlers.get(intent)
        if handler:
            return handler(query_lower)
        return self._general_query(query_lower)

    def _detect_intent_by_keywords(self, query_lower: str) -> dict:
        """Fallback keyword-based intent detection."""
        # Detect query intent - English keywords
        best_en = ["best", "top rated", "highest score", "top hotels", "good hotels"]
        worst_en = ["worst", "lowest score", "bad hotels", "poor hotels"]

        # Swahili keywords for hotel queries
        best_sw = ["bora", "nzuri", "vizuri", "safii", "top", "best"]
        worst_sw = ["mbaya", "chafu", "vibaya", "duni", "worst"]

        # Aspect keywords - English
        cleanliness_en = ["cleanliness", "clean", "hygiene", "dirty"]
        staff_en = ["staff", "service", "friendly", "reception"]
        location_en = ["location", "central", "area", "access"]
        value_en = ["value", "price", "money", "worth", "expensive", "cheap"]
        wifi_en = ["wifi", "internet", "connection", "signal"]
        noise_en = ["noise", "quiet", "loud", "silent"]
        food_en = ["food", "breakfast", "restaurant", "meal", "cuisine"]

        # Aspect keywords - Swahili
        cleanliness_sw = ["usafi", "safi", "chafu", "uchafu", "usafi wa"]
        staff_sw = ["wafanyakazi", "huduma", "karibu", "mpole", "staff"]
        location_sw = ["eneo", "mahali", "location", "mkabla"]
        value_sw = ["bei", "gharama", "value", "pesa", "ghali", "rahisi"]
        wifi_sw = ["wifi", "intaneti", "mtandao", "muunganisho"]
        noise_sw = ["kelele", "utulivu", "noise", "sauti"]
        food_sw = ["chakula", "kiamshakinywa", "chai", "meals", "food"]

        # Detect query intent and execute appropriate database query
        if any(word in query_lower for word in best_en + best_sw):
            return self._get_best_hotels(query_lower)
        elif any(word in query_lower for word in worst_en + worst_sw):
            return self._get_worst_hotels(query_lower)
        elif any(word in query_lower for word in cleanliness_en + cleanliness_sw):
            return self._get_hotels_by_aspect("cleanliness", query_lower)
        elif any(word in query_lower for word in staff_en + staff_sw):
            return self._get_hotels_by_aspect("staff", query_lower)
        elif any(word in query_lower for word in location_en + location_sw):
            return self._get_hotels_by_aspect("location", query_lower)
        elif any(word in query_lower for word in value_en + value_sw):
            return self._get_hotels_by_aspect("value", query_lower)
        elif any(word in query_lower for word in wifi_en + wifi_sw):
            return self._get_hotels_by_aspect("wifi", query_lower)
        elif any(word in query_lower for word in noise_en + noise_sw):
            return self._get_hotels_by_aspect("noise", query_lower)
        elif any(word in query_lower for word in food_en + food_sw):
            return self._get_hotels_by_aspect("food", query_lower)
        elif any(word in query_lower for word in ["complain", "negative", "malalamiko", "mbaya"]):
            return self._get_common_complaints(query_lower)
        elif "amsterdam" in query_lower:
            return self._get_hotels_in_city("Amsterdam", query_lower)
        else:
            return self._general_query(query_lower)

    def _get_best_hotels(self, query: str) -> dict:
        """Get hotels with highest reviewer scores."""
        from home.models import Review
        from django.db.models import Avg, Count

        hotels = (
            Review.objects
            .values("property_name", "property_id")
            .annotate(
                avg_score=Avg("reviewer_score"),
                review_count=Count("id")
            )
            .filter(review_count__gte=10)  # Minimum reviews for statistical significance
            .order_by("-avg_score")[:10]
        )

        hotels_list = [
            {"name": h["property_name"], "avg_score": float(h["avg_score"] or 0), "count": h["review_count"]}
            for h in hotels
        ]

        response = self.llm.generate_text(
            f"Based on these top hotels by reviewer score, provide a helpful summary: {hotels_list}"
        )

        return {"response": response, "data": {"hotels": hotels_list}}

    def _get_worst_hotels(self, query: str) -> dict:
        """Get hotels with lowest reviewer scores."""
        from home.models import Review
        from django.db.models import Avg, Count

        hotels = (
            Review.objects
            .values("property_name", "property_id")
            .annotate(
                avg_score=Avg("reviewer_score"),
                review_count=Count("id")
            )
            .filter(review_count__gte=10)
            .order_by("avg_score")[:10]
        )

        hotels_list = [
            {"name": h["property_name"], "avg_score": float(h["avg_score"] or 0), "count": h["review_count"]}
            for h in hotels
        ]

        response = self.llm.generate_text(
            f"Based on these lowest-rated hotels, provide a helpful summary: {hotels_list}"
        )

        return {"response": response, "data": {"hotels": hotels_list}}

    def _get_hotels_by_aspect(self, aspect: str, query: str) -> dict:
        """Get hotels rated highly on a specific aspect."""
        from home.models import Review
        from django.db.models import Avg, Count
        from django.db.models.functions import JSONObject

        # Query for hotels with good aspect scores
        hotels = (
            Review.objects
            .filter(is_processed=True, aspect_scores__has_key=aspect)
            .values("property_name", "property_id")
            .annotate(
                aspect_avg=Avg("aspect_scores"),
                review_count=Count("id")
            )
            .filter(review_count__gte=5)
            .order_by("-aspect_avg")[:10]
        )

        hotels_list = [
            {"name": h["property_name"], "aspect_score": float(h["aspect_avg"] or 0), "count": h["review_count"]}
            for h in hotels
        ]

        response = f"Here are the top hotels for {aspect} based on review analysis:"
        return {"response": response, "data": {"hotels": hotels_list}}

    def _get_common_complaints(self, query: str) -> dict:
        """Get most common complaint topics from negative reviews."""
        from home.models import Review, TopicCluster
        from django.db.models import Count

        # Get top negative topics
        topics = list(
            TopicCluster.objects
            .filter(avg_sentiment_score__lt=0.5)
            .order_by("avg_sentiment_score")[:10]
            .values("label", "review_count", "avg_sentiment_score")
        )

        response = "Based on review analysis, the most common complaints are:"
        return {"response": response, "data": {"topics": topics}}

    def _get_hotels_in_city(self, city: str, query: str) -> dict:
        """Get hotels in a specific city."""
        from home.models import Review
        from django.db.models import Avg, Count

        hotels = (
            Review.objects
            .filter(property_name__icontains=city)
            .values("property_name", "property_id")
            .annotate(
                avg_score=Avg("reviewer_score"),
                review_count=Count("id")
            )
            .order_by("-avg_score")[:10]
        )

        hotels_list = [
            {"name": h["property_name"], "avg_score": float(h["avg_score"] or 0), "count": h["review_count"]}
            for h in hotels
        ]

        response = f"Here are the top-rated hotels in {city}:"
        return {"response": response, "data": {"hotels": hotels_list}}

    def _general_query(self, query: str) -> dict:
        """Handle general queries using LLM with database context."""
        from home.models import Review
        from django.db.models import Count, Avg

        # Get some general stats to provide context
        stats = {
            "total_reviews": Review.objects.count(),
            "total_hotels": Review.objects.values("property_name").distinct().count(),
            "avg_score": float(Review.objects.filter(reviewer_score__isnull=False).aggregate(Avg("reviewer_score"))["reviewer_score__avg"] or 0),
        }

        response = self.llm.generate_text(
            f"Answer this question about our hotel review database: '{query}'. "
            f"Here are some stats: {stats}. Provide a helpful response."
        )

        return {"response": response, "data": {"stats": stats}}

