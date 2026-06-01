"""
Multi-Model LLM Service for sentiment analysis, topic extraction, and insights.
Distributes load across Groq, Mistral, and OpenRouter for reliability and cost optimization.
Optimized for East African hospitality context with Swahili language support.
"""

import json
import os
import logging
import hashlib
from functools import lru_cache
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ModelProvider(Enum):
    GROQ = "groq"
    MISTRAL = "mistral"
    OPENROUTER = "openrouter"
    FALLBACK = "fallback"


@dataclass
class ModelConfig:
    """Configuration for a model provider."""
    provider: ModelProvider
    model_name: str
    api_key_env: str
    api_base: Optional[str] = None
    max_tokens: int = 2000
    temperature: float = 0.3
    weight: int = 1  # For load balancing


# Model configurations with load balancing weights
# Note: OpenRouter uses Google's Gemini which has excellent Swahili support
MODEL_CONFIGS = [
    ModelConfig(
        provider=ModelProvider.GROQ,
        model_name="llama-3.3-70b-versatile",
        api_key_env="GROQ_API_KEY",
        weight=2,  # Primary provider (2/5 of requests)
    ),
    ModelConfig(
        provider=ModelProvider.OPENROUTER,
        model_name="google/gemini-3.5-flash",
        api_key_env="OPENROUTER_API_KEY",
        weight=3,  # Secondary provider with Swahili support (3/5 of requests)
    ),
]

# OpenRouter API endpoint
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


class MultiModelLLMService:
    """
    Multi-model LLM service with load balancing and failover.
    Distributes requests across multiple providers for reliability and cost optimization.
    """

    def __init__(self):
        self.configs = []
        self.clients = {}
        self._response_cache = {}
        self._cache_ttl = 300  # 5 minutes
        self._request_counter = 0
        
        # Initialize available providers
        for config in MODEL_CONFIGS:
            api_key = os.environ.get(config.api_key_env, "")
            if api_key:
                self.configs.append(config)
                self._init_client(config, api_key)
        
        if not self.configs:
            logger.warning("No LLM API keys configured. Using fallback mode only.")

    def _init_client(self, config: ModelConfig, api_key: str):
        """Initialize client for a specific provider."""
        try:
            if config.provider == ModelProvider.GROQ:
                from groq import Groq
                # Fix: Set explicit base_url to avoid URL duplication bug
                self.clients[config.provider] = Groq(
                    api_key=api_key,
                    base_url="https://api.groq.com"
                )
            elif config.provider == ModelProvider.MISTRAL:
                from mistralai import Mistral
                self.clients[config.provider] = Mistral(api_key=api_key)
            elif config.provider == ModelProvider.OPENROUTER:
                # Store API key for direct requests module usage
                self.clients[config.provider] = {"api_key": api_key}
        except Exception as e:
            logger.error(f"Failed to initialize {config.provider.value} client: {e}")

    def _get_cache_key(self, text: str, task_type: str) -> str:
        """Generate a cache key for LLM responses."""
        return f"{task_type}:{hashlib.md5(text.encode()).hexdigest()}"

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
    
    def generate_text(self, prompt: str, temperature: float = 0.3, max_tokens: int = 500) -> Optional[str]:
        """Alias for _call_with_failover for backward compatibility."""
        return self._call_with_failover(prompt, temperature=temperature, max_tokens=max_tokens)

    def _set_cache(self, key: str, response: Any) -> None:
        """Cache LLM response with timestamp."""
        self._response_cache[key] = (response, datetime.now().timestamp())

    def _select_provider(self) -> Optional[ModelConfig]:
        """
        Select provider using weighted round-robin load balancing.
        """
        if not self.configs:
            return None
        
        # Simple weighted selection based on request counter
        total_weight = sum(c.weight for c in self.configs)
        position = self._request_counter % total_weight
        self._request_counter += 1
        
        cumulative = 0
        for config in self.configs:
            cumulative += config.weight
            if position < cumulative:
                return config
        
        return self.configs[0]  # Fallback to first

    def _call_llm(
        self,
        prompt: str,
        config: ModelConfig,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        json_response: bool = False,
    ) -> Optional[str]:
        """Call LLM with specific provider config."""
        try:
            client = self.clients.get(config.provider)
            if not client:
                return None

            if config.provider == ModelProvider.GROQ:
                response = client.chat.completions.create(
                    model=config.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=min(max_tokens, config.max_tokens),
                    response_format={"type": "json_object"} if json_response else None,
                )
                return response.choices[0].message.content

            elif config.provider == ModelProvider.MISTRAL:
                response = client.chat.complete(
                    model=config.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=min(max_tokens, config.max_tokens),
                    response_format="json_object" if json_response else None,
                )
                return response.choices[0].message.content

            elif config.provider == ModelProvider.OPENROUTER:
                import requests
                api_key = client.get("api_key", "")
                
                payload = {
                    "model": config.model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                    "max_tokens": min(max_tokens, config.max_tokens),
                }
                if json_response:
                    payload["response_format"] = {"type": "json_object"}
                
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                }
                
                response = requests.post(
                    OPENROUTER_API_URL,
                    headers=headers,
                    json=payload,
                    timeout=30
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]

        except Exception as e:
            logger.warning(f"{config.provider.value} call failed: {e}")
            return None
        
        return None

    def _call_with_failover(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        json_response: bool = False,
    ) -> Optional[str]:
        """
        Call LLM with automatic failover across providers.
        Tries providers in order of preference until one succeeds.
        """
        # Try weighted selection first
        config = self._select_provider()
        if not config:
            return None
        
        # Build ordered list of providers to try (selected first, then others)
        providers_to_try = [config] + [c for c in self.configs if c != config]
        
        for provider_config in providers_to_try:
            result = self._call_llm(
                prompt, provider_config, temperature, max_tokens, json_response
            )
            if result:
                return result
        
        return None

    def sentiment_analysis(
        self, text: str, language: str = "en", context: str = "east_africa"
    ) -> Dict[str, Any]:
        """
        Analyze sentiment of text with East African context awareness.
        Returns: {"sentiment": "positive|negative|neutral", "score": 0.0-1.0, "reasoning": "..."}
        """
        cache_key = self._get_cache_key(text, "sentiment")
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            lang_context = "Swahili" if language == "sw" else "English"
            
            # East African context prompt
            context_prompt = ""
            if context == "east_africa":
                context_prompt = """
IMPORTANT: This review is from East Africa (Kenya, Tanzania, Uganda, Rwanda, Burundi).
Consider local hospitality norms:
- "Pole pole" (slowly) is normal pace, not necessarily negative
- "Hakuna matata" culture means relaxed service is expected
- Swahili phrases mixed with English are common
- Local food preferences differ from Western standards
- Safety concerns may differ from European contexts
"""

            prompt = f"""Analyze the sentiment of this {lang_context} hospitality review from East Africa.
Return ONLY a JSON object with no markdown:
{{"sentiment": "positive" or "negative" or "neutral", "score": 0.0-1.0, "reasoning": "brief reason"}}

{context_prompt}
Review: {text}"""

            result_str = self._call_with_failover(
                prompt, temperature=0.3, max_tokens=200, json_response=True
            )
            
            if result_str:
                result = json.loads(result_str)
                self._set_cache(cache_key, result)
                return result

        except Exception as e:
            logger.error(f"Sentiment analysis failed: {e}")
        
        return {
            "sentiment": "neutral",
            "score": 0.5,
            "reasoning": "Analysis failed, using neutral default",
        }

    def extract_topics(
        self, text: str, property_name: str = "", context: str = "east_africa"
    ) -> Dict[str, Any]:
        """
        Extract topics and aspects from review text with East African context.
        Returns: {"topics": ["..."], "key_phrases": ["..."], "aspect_scores": {...}}
        """
        cache_key = self._get_cache_key(text, "topics")
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            context_prompt = ""
            if context == "east_africa":
                context_prompt = """
EAST AFRICAN CONTEXT:
- Consider local hospitality aspects: "karibu" (welcome), "pole" (sorry/empathy)
- Safety concerns: wildlife, local area safety, water quality
- Infrastructure: power outages, water supply, internet reliability
- Cultural experiences: local tours, cultural villages, community visits
- Food: local cuisine (ugali, nyama choma), dietary accommodations
- Transport: safari arrangements, airport transfers, local taxis
"""

            prompt = f"""Extract topics and aspect scores from this East African hospitality review.
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
    "noise": 0.0-1.0,
    "safety": 0.0-1.0,
    "cultural_experience": 0.0-1.0
  }}
}}

Property: {property_name}

{context_prompt}
Review: {text}"""

            result_str = self._call_with_failover(
                prompt, temperature=0.3, max_tokens=500, json_response=True
            )
            
            if result_str:
                result = json.loads(result_str)
                self._set_cache(cache_key, result)
                return result

        except Exception as e:
            logger.error(f"Topic extraction failed: {e}")
        
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
        location: str = "East Africa",
    ) -> Dict[str, str]:
        """
        Generate LLM narrative insight for a property with East African context.
        """
        cache_key = f"insight:{property_name}:{total_reviews}:{avg_score}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            context = f"""
Property: {property_name}
Location: {location}
Total Reviews: {total_reviews}
Average Score: {avg_score}/10
Sentiment Breakdown: {json.dumps(sentiment_breakdown)}
Top Topics: {', '.join(top_topics[:5])}
Aspect Averages: {json.dumps(aspect_averages, indent=2)}
Swahili Feedback: {swahili_feedback_count} reviews

EAST AFRICAN CONTEXT:
- Consider local hospitality standards and guest expectations
- Factor in regional challenges (infrastructure, seasonal variations)
- Highlight cultural strengths and community engagement
- Address safety and health considerations specific to the region
"""

            prompt = f"""You are a hospitality analytics expert specializing in East African tourism.
Generate insights for this property.

Return ONLY JSON with no markdown:
{{
  "strength_summary": "What guests love about this property (2-3 sentences, consider East African context)",
  "weakness_summary": "What guests dislike (2-3 sentences, consider regional challenges)",
  "actionable_advice": "Top 3-5 specific improvements considering East African tourism standards",
  "overall_narrative": "One paragraph summary for property managers, highlighting East African hospitality strengths"
}}

{context}"""

            result_str = self._call_with_failover(
                prompt, temperature=0.3, max_tokens=800, json_response=True
            )
            
            if result_str:
                result = json.loads(result_str)
                self._set_cache(cache_key, result)
                return result

        except Exception as e:
            logger.error(f"Insight generation failed: {e}")
        
        return {
            "strength_summary": "",
            "weakness_summary": "",
            "actionable_advice": "",
            "overall_narrative": "",
        }

    def answer_query(
        self, query: str, data: Dict[str, Any], history: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        Answer natural language queries about hotel data with East African context.
        """
        try:
            context_prompt = ""
            if "east africa" in query.lower() or "tanzania" in query.lower() or "kenya" in query.lower():
                context_prompt = """
CONTEXT: This data is from East African hospitality properties.
Consider local factors:
- Safari tourism patterns
- Seasonal variations (wet/dry seasons)
- Cultural hospitality norms
- Regional safety considerations
- Local economic factors affecting value perception
"""

            prompt = f"""Answer this question about East African hotel reviews.
{context_prompt}
Data: {json.dumps(data, indent=2)}
Question: {query}

Provide a helpful, detailed response with specific data points."""

            response = self._call_with_failover(
                prompt, temperature=0.4, max_tokens=500, json_response=False
            )
            
            return {
                "response": response or "I couldn't process that query.",
                "data": data,
            }

        except Exception as e:
            logger.error(f"Query answering failed: {e}")
            return {
                "response": "Sorry, I encountered an error processing your query.",
                "data": {},
            }


# Global instance
_llm_service = MultiModelLLMService()


# Convenience functions
def sentiment_analysis(text: str, language: str = "en") -> Dict[str, Any]:
    """Analyze sentiment using multi-model service."""
    return _llm_service.sentiment_analysis(text, language)


def extract_topics(text: str, property_name: str = "") -> Dict[str, Any]:
    """Extract topics using multi-model service."""
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
    """Generate property insight using multi-model service."""
    return _llm_service.generate_property_insight(
        property_name,
        total_reviews,
        avg_score,
        sentiment_breakdown,
        top_topics,
        aspect_averages,
        swahili_feedback_count,
    )


def answer_query(query: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Answer natural language queries using multi-model service."""
    return _llm_service.answer_query(query, data)



# Alias for backward compatibility with views.py
LLMService = MultiModelLLMService

