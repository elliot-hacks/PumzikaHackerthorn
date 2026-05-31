"""
Groq LLM Service for sentiment analysis, topic extraction, and insights.
Integrates with Groq API (llama-3.3-70b-versatile) with caching and error handling.
"""

import json
import os
import logging
from functools import lru_cache
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta

from groq import Groq

logger = logging.getLogger(__name__)


class GroqLLMService:
    """Wrapper around Groq API for NLP tasks."""

    def __init__(self):
        self.api_key = os.environ.get("GROQ_API_KEY", "")
        if not self.api_key:
            logger.warning("GROQ_API_KEY not set. LLM features will not work.")
        self.client = Groq(api_key=self.api_key) if self.api_key else None
        self._response_cache = {}
        self._cache_ttl = 300  # 5 minutes

    def _get_cache_key(self, text: str, task_type: str) -> str:
        """Generate a cache key for LLM responses."""
        return f"{task_type}:{hash(text)}"

    def _is_cache_valid(self, timestamp: float) -> bool:
        """Check if cached response is still valid."""
        return (datetime.now().timestamp() - timestamp) < self._cache_ttl

    def _get_cached(self, key: str) -> Optional[Any]:
        """Retrieve cached response if valid."""
        if key in self._response_cache:
            response, timestamp = self._response_cache[key]
            if self._is_cache_valid(timestamp):
                return response
            else:
                del self._response_cache[key]
        return None

    def _set_cache(self, key: str, response: Any) -> None:
        """Cache LLM response with timestamp."""
        self._response_cache[key] = (response, datetime.now().timestamp())

    def sentiment_analysis(
        self, text: str, language: str = "en"
    ) -> Dict[str, Any]:
        """
        Analyze sentiment of text.
        Returns: {"sentiment": "positive|negative|neutral", "score": 0.0-1.0, "reasoning": "..."}
        """
        if not self.client:
            return {
                "sentiment": "neutral",
                "score": 0.5,
                "reasoning": "LLM not configured",
            }

        cache_key = self._get_cache_key(text, "sentiment")
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            lang_context = (
                "Swahili" if language == "sw" else "English"
            )
            prompt = f"""Analyze the sentiment of this {lang_context} hospitality review.
Return ONLY a JSON object with no markdown:
{{"sentiment": "positive" or "negative" or "neutral", "score": 0.0-1.0, "reasoning": "brief reason"}}

Review: {text}"""

            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=200,
                response_format={"type": "json_object"},
            )

            result = json.loads(response.choices[0].message.content)
            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Groq sentiment analysis failed: {e}")
            return {
                "sentiment": "neutral",
                "score": 0.5,
                "reasoning": f"Error: {str(e)[:50]}",
            }

    def extract_topics(
        self, text: str, property_name: str = ""
    ) -> Dict[str, Any]:
        """
        Extract topics and aspects from review text.
        Returns: {"topics": ["..."], "key_phrases": ["..."], "aspect_scores": {"cleanliness": 0.8, ...}}
        """
        if not self.client:
            return {
                "topics": [],
                "key_phrases": [],
                "aspect_scores": {},
            }

        cache_key = self._get_cache_key(text, "topics")
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            prompt = f"""Extract topics and aspect scores from this hospitality review.
Return ONLY JSON with no markdown:
{{
  "topics": ["topic1", "topic2"],
  "key_phrases": ["phrase1", "phrase2"],
  "aspect_scores": {{
    "cleanliness": 0.0-1.0,
    "staff": 0.0-1.0,
    "location": 0.0-1.0,
    "value": 0.0-1.0,
    "amenities": 0.0-1.0,
    "wifi": 0.0-1.0,
    "food": 0.0-1.0,
    "noise": 0.0-1.0
  }}
}}

Property: {property_name}
Review: {text}"""

            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500,
                response_format={"type": "json_object"},
            )

            result = json.loads(response.choices[0].message.content)
            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Groq topic extraction failed: {e}")
            return {
                "topics": [],
                "key_phrases": [],
                "aspect_scores": {},
            }

    def generate_property_insight(
        self,
        property_name: str,
        total_reviews: int,
        avg_score: float,
        sentiment_breakdown: Dict[str, int],
        top_topics: List[str],
        aspect_averages: Dict[str, float],
        swahili_feedback_count: int = 0,
    ) -> Dict[str, str]:
        """
        Generate LLM narrative insight for a property.
        Returns: {"strength_summary": "...", "weakness_summary": "...", "actionable_advice": "...", "overall_narrative": "..."}
        """
        if not self.client:
            return {
                "strength_summary": "",
                "weakness_summary": "",
                "actionable_advice": "",
                "overall_narrative": "",
            }

        cache_key = f"insight:{property_name}:{total_reviews}:{avg_score}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            context = f"""
Property: {property_name}
Total Reviews: {total_reviews}
Average Score: {avg_score}/10
Sentiment Breakdown: {json.dumps(sentiment_breakdown)}
Top Topics: {', '.join(top_topics[:5])}
Aspect Averages: {json.dumps(aspect_averages, indent=2)}
Swahili Feedback: {swahili_feedback_count} reviews
"""

            prompt = f"""You are a hospitality analytics expert. Generate insights for a property.
Return ONLY JSON with no markdown:
{{
  "strength_summary": "What guests love about this property (2-3 sentences)",
  "weakness_summary": "What guests dislike (2-3 sentences)",
  "actionable_advice": "Top 3-5 specific improvements the property should make",
  "overall_narrative": "One paragraph summary for property managers"
}}

{context}"""

            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=800,
                response_format={"type": "json_object"},
            )

            result = json.loads(response.choices[0].message.content)
            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Groq insight generation failed: {e}")
            return {
                "strength_summary": "",
                "weakness_summary": "",
                "actionable_advice": "",
                "overall_narrative": "",
            }

    def semantic_search(
        self, query: str, candidates: List[str], limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Find semantically similar candidates to the query using LLM.
        Returns: [{"text": "...", "relevance": 0.0-1.0, "reason": "..."}, ...]
        """
        if not self.client or not candidates:
            return []

        try:
            candidates_str = "\n".join(
                [f"{i+1}. {c[:200]}" for i, c in enumerate(candidates[:20])]
            )
            prompt = f"""Find the top {limit} most semantically similar items to the query.
Return ONLY JSON array with no markdown:
[
  {{"index": 1, "relevance": 0.95, "reason": "explanation"}}
]

Query: {query}

Candidates:
{candidates_str}"""

            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=300,
                response_format={"type": "json_object"},
            )

            results_raw = json.loads(response.choices[0].message.content)
            results = []
            for item in results_raw:
                idx = item.get("index", 0) - 1
                if 0 <= idx < len(candidates):
                    results.append(
                        {
                            "text": candidates[idx],
                            "relevance": item.get("relevance", 0.5),
                            "reason": item.get("reason", ""),
                        }
                    )
            return results[:limit]

        except Exception as e:
            logger.error(f"Groq semantic search failed: {e}")
            return []


# Global instance
_llm_service = GroqLLMService()


def sentiment_analysis(text: str, language: str = "en") -> Dict[str, Any]:
    """Analyze sentiment using Groq."""
    return _llm_service.sentiment_analysis(text, language)


def extract_topics(text: str, property_name: str = "") -> Dict[str, Any]:
    """Extract topics using Groq."""
    return _llm_service.extract_topics(text, property_name)


def generate_property_insight(
    property_name: str,
    total_reviews: int,
    avg_score: float,
    sentiment_breakdown: Dict[str, int],
    top_topics: List[str],
    aspect_averages: Dict[str, float],
    swahili_feedback_count: int = 0,
) -> Dict[str, str]:
    """Generate property insight using Groq."""
    return _llm_service.generate_property_insight(
        property_name,
        total_reviews,
        avg_score,
        sentiment_breakdown,
        top_topics,
        aspect_averages,
        swahili_feedback_count,
    )


def semantic_search(
    query: str, candidates: List[str], limit: int = 5
) -> List[Dict[str, Any]]:
    """Semantic search using Groq."""
    return _llm_service.semantic_search(query, candidates, limit)
