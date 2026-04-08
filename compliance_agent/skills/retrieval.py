"""Retrieval skills."""

from __future__ import annotations

import math
import re
from collections import Counter

try:
    from rank_bm25 import BM25Okapi
except ImportError:  # pragma: no cover - exercised indirectly in environments without rank_bm25
    BM25Okapi = None

from .. import config
from .registry import Skill


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\b[a-z0-9]{2,}\b", text.lower())


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for value in values:
        cleaned = value.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        deduped.append(cleaned)
    return deduped


def expand_query(requirement_text: str) -> list[str]:
    """Generate expanded retrieval queries from one requirement sentence."""
    queries = [requirement_text]
    first_sentence = requirement_text.split(".")[0].strip()
    if first_sentence and first_sentence != requirement_text:
        queries.append(first_sentence)

    acronyms = re.findall(r"\b[A-Z]{2,}\b", requirement_text)
    numbers = re.findall(r"\d+[\.\d]*\s*(?:%|percent|hours?|days?|minutes?)", requirement_text, flags=re.IGNORECASE)
    if acronyms or numbers:
        queries.append(" ".join(acronyms + numbers))

    lowered = requirement_text.lower()
    domain_expansions = {
        "fedramp": "federal risk authorization security assessment",
        "sla": "service level agreement uptime response time",
        "encryption": "aes-256 key management at rest in transit",
        "incident": "incident response breach notification root cause",
        "availability": "uptime resilience failover high availability",
    }
    for term, expansion in domain_expansions.items():
        if term in lowered:
            queries.append(expansion)

    return _dedupe_preserve_order(queries)


def _cosine_score(query_tokens: list[str], chunk_tokens: list[str]) -> float:
    query_counter = Counter(query_tokens)
    chunk_counter = Counter(chunk_tokens)
    vocabulary = set(query_counter) | set(chunk_counter)
    dot = sum(query_counter[token] * chunk_counter[token] for token in vocabulary)
    query_norm = math.sqrt(sum(value * value for value in query_counter.values()))
    chunk_norm = math.sqrt(sum(value * value for value in chunk_counter.values()))
    if not query_norm or not chunk_norm:
        return 0.0
    return dot / (query_norm * chunk_norm)


def _normalize_scores(results: list[dict], score_key: str) -> list[dict]:
    max_score = max((item.get(score_key, 0.0) for item in results), default=0.0)
    if max_score <= 0:
        return [{**item, f"normalized_{score_key}": 0.0} for item in results]
    return [
        {**item, f"normalized_{score_key}": item.get(score_key, 0.0) / max_score}
        for item in results
    ]


def _fallback_bm25_score(query_tokens: list[str], chunk_tokens: list[str]) -> float:
    if not query_tokens or not chunk_tokens:
        return 0.0
    chunk_counter = Counter(chunk_tokens)
    overlap = 0.0
    for token in query_tokens:
        if token in chunk_counter:
            overlap += 1.0 + math.log1p(chunk_counter[token])
    return overlap / len(set(query_tokens))


def _resolve_weights(weights: dict | None = None) -> dict:
    weights = weights or {}
    semantic = float(weights.get("semantic", 0.5))
    lexical = float(weights.get("lexical", 0.5))
    total = semantic + lexical
    if total <= 0:
        return {"semantic": 0.5, "lexical": 0.5}
    return {
        "semantic": semantic / total,
        "lexical": lexical / total,
    }


async def vector_search(
    requirement_text: str,
    corpus_chunks: list[dict],
    top_k: int = config.TOP_K_RETRIEVAL,
    query_texts: list[str] | None = None,
) -> dict:
    expanded_queries = query_texts or [requirement_text]
    scored_by_chunk: dict[str, dict] = {}
    for query in expanded_queries:
        query_tokens = _tokenize(query)
        for chunk in corpus_chunks:
            chunk_tokens = _tokenize(chunk.get("text", ""))
            score = _cosine_score(query_tokens, chunk_tokens)
            if score <= 0:
                continue
            chunk_id = chunk.get("chunk_id")
            existing = scored_by_chunk.get(chunk_id)
            if existing is None or score > existing["retrieval_score"]:
                scored_by_chunk[chunk_id] = {**chunk, "retrieval_score": score, "retrieval_source": "vector"}
    scored = list(scored_by_chunk.values())
    scored.sort(key=lambda item: item["retrieval_score"], reverse=True)
    return {"results": scored[:top_k]}


async def bm25_search(
    requirement_text: str,
    corpus_chunks: list[dict],
    top_k: int = config.BM25_TOP_K,
    query_texts: list[str] | None = None,
) -> dict:
    tokenized_corpus = [_tokenize(chunk.get("text", "")) for chunk in corpus_chunks]
    expanded_queries = query_texts or [requirement_text]
    ranked_by_chunk: dict[str, dict] = {}
    bm25 = BM25Okapi(tokenized_corpus or [[]]) if BM25Okapi is not None else None
    for query in expanded_queries:
        query_tokens = _tokenize(query)
        if bm25 is not None:
            scores = bm25.get_scores(query_tokens)
        else:
            scores = [_fallback_bm25_score(query_tokens, chunk_tokens) for chunk_tokens in tokenized_corpus]
        for chunk, score in zip(corpus_chunks, scores):
            if score <= 0:
                continue
            chunk_id = chunk.get("chunk_id")
            existing = ranked_by_chunk.get(chunk_id)
            score_float = float(score)
            if existing is None or score_float > existing["retrieval_score"]:
                ranked_by_chunk[chunk_id] = {**chunk, "retrieval_score": score_float, "retrieval_source": "bm25"}

    ranked = sorted(ranked_by_chunk.values(), key=lambda item: item["retrieval_score"], reverse=True)
    return {"results": ranked[:top_k]}


async def rerank(
    vector_results: list[dict],
    bm25_results: list[dict],
    top_k: int = config.RERANK_TOP_K,
    weights: dict | None = None,
) -> dict:
    resolved_weights = _resolve_weights(weights)
    vector_results = _normalize_scores(vector_results, "retrieval_score")
    bm25_results = _normalize_scores(bm25_results, "retrieval_score")
    merged: dict[str, dict] = {}
    for result in vector_results:
        semantic_score = result.get("normalized_retrieval_score", 0.0)
        merged[result["chunk_id"]] = {
            **result,
            "semantic_score": semantic_score,
            "lexical_score": 0.0,
            "hybrid_score": semantic_score * resolved_weights["semantic"],
        }
    for result in bm25_results:
        lexical_score = result.get("normalized_retrieval_score", 0.0)
        if result["chunk_id"] in merged:
            merged[result["chunk_id"]]["lexical_score"] = lexical_score
            merged[result["chunk_id"]]["hybrid_score"] += lexical_score * resolved_weights["lexical"]
            merged[result["chunk_id"]]["retrieval_source"] = "hybrid"
        else:
            merged[result["chunk_id"]] = {
                **result,
                "semantic_score": 0.0,
                "lexical_score": lexical_score,
                "hybrid_score": lexical_score * resolved_weights["lexical"],
            }

    ranked = sorted(merged.values(), key=lambda item: item["hybrid_score"], reverse=True)
    return {"results": ranked[:top_k]}


async def assemble_context(
    requirements: list[dict],
    corpus_chunks: list[dict],
    retrieval_plans: dict | None = None,
) -> dict:
    retrieval_plans = retrieval_plans or {}
    evidence_map = {}
    for requirement in requirements:
        plan = retrieval_plans.get(requirement["req_id"], {})
        query_texts = (
            expand_query(requirement["requirement_text"])
            if plan.get("expand_queries")
            else [requirement["requirement_text"]]
        )
        vector = await vector_search(
            requirement["requirement_text"],
            corpus_chunks,
            int(plan.get("semantic_top_k", config.TOP_K_RETRIEVAL)),
            query_texts=query_texts,
        )
        lexical = await bm25_search(
            requirement["requirement_text"],
            corpus_chunks,
            int(plan.get("lexical_top_k", config.BM25_TOP_K)),
            query_texts=query_texts,
        )
        reranked = await rerank(
            vector["results"],
            lexical["results"],
            int(plan.get("top_k", config.RERANK_TOP_K)),
            weights=plan.get("weights"),
        )
        annotated = []
        for item in reranked["results"]:
            annotated.append({
                **item,
                "retrieval_strategy": plan.get("strategy", "hybrid"),
                "retrieval_weights": _resolve_weights(plan.get("weights")),
                "retrieval_queries": query_texts,
            })
        evidence_map[requirement["req_id"]] = annotated
    return {"evidence_map": evidence_map}


def register_skills(registry):
    registry.register(Skill(
        name="vector_search",
        description="Approximate semantic retrieval over a chunk corpus.",
        handler=vector_search,
        input_schema={"requirement_text": "str", "corpus_chunks": "list[dict]", "top_k": "int"},
        output_schema={"results": "list[dict]"},
        tags=["retrieval", "semantic"],
        llm_tier="none",
    ))
    registry.register(Skill(
        name="bm25_search",
        description="Lexical BM25 retrieval over a chunk corpus.",
        handler=bm25_search,
        input_schema={"requirement_text": "str", "corpus_chunks": "list[dict]", "top_k": "int"},
        output_schema={"results": "list[dict]"},
        tags=["retrieval", "bm25", "lexical"],
        llm_tier="none",
    ))
    registry.register(Skill(
        name="rerank",
        description="Combine semantic and lexical retrieval results into a reranked list.",
        handler=rerank,
        input_schema={"vector_results": "list[dict]", "bm25_results": "list[dict]", "top_k": "int", "weights": "dict|null"},
        output_schema={"results": "list[dict]"},
        tags=["retrieval", "rerank"],
        llm_tier="none",
    ))
    registry.register(Skill(
        name="assemble_context",
        description="Build a requirement-to-evidence map using hybrid retrieval.",
        handler=assemble_context,
        input_schema={"requirements": "list[dict]", "corpus_chunks": "list[dict]", "retrieval_plans": "dict|null"},
        output_schema={"evidence_map": "dict"},
        tags=["retrieval", "hybrid", "context"],
        llm_tier="none",
    ))
