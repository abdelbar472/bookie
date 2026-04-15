"""Ranking helpers for recommendation service."""

from typing import Any, Dict, List


def rank_unique_recommendations(all_results: List[Dict[str, Any]], user_history: List[str]) -> List[Dict[str, Any]]:
    seen = set(user_history)
    unique_results: List[Dict[str, Any]] = []

    for result in all_results:
        work_id = result.get("work_id")
        if work_id and work_id not in seen:
            seen.add(work_id)
            unique_results.append(result)

    unique_results.sort(key=lambda item: item.get("score", 0), reverse=True)
    return unique_results


def diversify_by_genre(results: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
    if not results:
        return results

    genre_counts: Dict[str, int] = {}
    diversified: List[Dict[str, Any]] = []

    for result in results:
        genres = result.get("genres") or ["Unknown"]
        primary_genre = genres[0] if genres else "Unknown"
        if genre_counts.get(primary_genre, 0) < 2:
            diversified.append(result)
            genre_counts[primary_genre] = genre_counts.get(primary_genre, 0) + 1
        if len(diversified) >= top_k:
            break

    if len(diversified) < top_k:
        for result in results:
            if result not in diversified:
                diversified.append(result)
            if len(diversified) >= top_k:
                break

    return diversified

