# home/utils.py
from unfold.dataclasses import SearchResult
from home.nlp import NLPQueryEngine

_engine = None

def _get_engine():
    global _engine
    if _engine is None:
        _engine = NLPQueryEngine()
    return _engine

def nlp_search_callback(request, search_term):
    if not search_term or len(search_term) < 3:
        return []

    try:
        result = _get_engine().process_query(search_term)
        hotels = result.get("data", {}).get("hotels", [])

        if not hotels:
            return [SearchResult(
                title=result.get("response", "No results"),
                description="Try: 'Hoteli bora', 'best food', 'cleanliness'",
                link="/admin/home/review/",
                icon="hotel",
            )]

        return [
            SearchResult(
                title=h["name"],
                description=f"Score: {h.get('avg_score') or h.get('aspect_score', 0):.2f}",
                link=f"/admin/home/review/?property_name={h['name']}",
                icon="star",
            )
            for h in hotels[:10]
        ]

    except Exception:
        return []

        