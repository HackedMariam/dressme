"""
Pagination - one response envelope for every list endpoint.
The list keeps its historical key ("products", "items") so existing clients keep working;
total / limit / offset / has_more / next_offset are added next to it.
"""

from typing import Any, Dict, List, Optional, Sequence

from fastapi import Query

MAX_LIMIT = 200


class PageParams:
    """FastAPI dependency: ?limit=&offset= with bounds (limit 1-200, offset >= 0)"""

    def __init__(self, limit: int = Query(50, ge=1, le=MAX_LIMIT, description="Items per page (1-200)"),
                 offset: int = Query(0, ge=0, le=1_000_000, description="Items to skip")):
        self.limit = limit
        self.offset = offset


def page_envelope(items: List[Any], total: int, limit: int, offset: int, key: str = "items",
                  extra: Optional[Dict] = None) -> Dict:
    next_offset = offset + len(items)
    envelope = {
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": next_offset < total,
        "next_offset": next_offset if next_offset < total else None,
        key: items,
    }
    if extra:
        envelope.update(extra)
    return envelope


def paginate(sequence: Sequence[Any], limit: int, offset: int, key: str = "items", extra: Optional[Dict] = None) -> Dict:
    """Paginate an in-memory sequence (the catalog lives in memory - 761 rows)"""
    return page_envelope(list(sequence[offset:offset + limit]), len(sequence), limit, offset, key, extra)
