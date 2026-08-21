"""Candidate graph: identity, grouping, alternatives, conflicts — not storage."""

from __future__ import annotations

from uuid import UUID

from webmedia_dl.domain.enums import MediaKind
from webmedia_dl.domain.models import CandidateGraph, GraphEdge, MediaCandidate

KIND_RANK = {
    MediaKind.VIDEO: 0,
    MediaKind.LIVE_STREAM: 1,
    MediaKind.AUDIO: 2,
    MediaKind.IMAGE: 3,
    MediaKind.GALLERY: 4,
    MediaKind.DOCUMENT: 5,
    MediaKind.SUBTITLE: 6,
    MediaKind.UNKNOWN: 7,
    MediaKind.PAGE: 8,
}


def build_graph(job_id: UUID, candidates: list[MediaCandidate]) -> CandidateGraph:
    edges: list[GraphEdge] = []
    by_group: dict[str, list[MediaCandidate]] = {}
    for candidate in candidates:
        key = candidate.grouping_key or candidate.host or "ungrouped"
        by_group.setdefault(key, []).append(candidate)
    for group in by_group.values():
        if len(group) < 2:
            continue
        head = group[0]
        for other in group[1:]:
            edges.append(
                GraphEdge(
                    from_id=other.candidate_id, to_id=head.candidate_id, relation="grouped_with"
                )
            )
            if other.media_kind == head.media_kind:
                edges.append(
                    GraphEdge(
                        from_id=other.candidate_id,
                        to_id=head.candidate_id,
                        relation="alternative_of",
                    )
                )
    identity_counts: dict[str, int] = {}
    for candidate in candidates:
        identity_counts[candidate.identity_key] = identity_counts.get(candidate.identity_key, 0) + 1
    conflicts = [f"duplicate-identity:{key}" for key, count in identity_counts.items() if count > 1]
    for candidate in candidates:
        if candidate.drm_signals:
            conflicts.append(f"drm:{candidate.identity_key}")
    return CandidateGraph(job_id=job_id, nodes=candidates, edges=edges, conflicts=conflicts)


def preferred_candidates(graph: CandidateGraph) -> list[MediaCandidate]:
    """Prefer non-page, non-DRM candidates. Discovery does not decide acquisition."""
    clean = [node for node in graph.nodes if not node.drm_signals]
    pool = clean or list(graph.nodes)
    return sorted(pool, key=lambda node: KIND_RANK.get(node.media_kind, 7))
