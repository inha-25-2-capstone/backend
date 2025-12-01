"""
Press (news organizations) API endpoints.
"""
from fastapi import APIRouter, HTTPException, Query, status
from typing import Optional, List, Dict, Any, Tuple
import logging
import math

from src.api.schemas import (
    PressInfo,
    PressDetail,
    ArticleSummary,
    PaginatedResponse,
    PaginationMeta,
    StanceDistribution,
    StanceType,
)
from src.api.utils import run_in_executor
from src.models.database import get_db_cursor

logger = logging.getLogger(__name__)

router = APIRouter()


def _fetch_all_press(sort_order: str) -> List[Dict[str, Any]]:
    """Synchronous function to fetch all press with article counts."""
    with get_db_cursor() as cur:
        # Fetch all press with article count in one query
        query = f"""
            SELECT
                p.press_id,
                p.press_name,
                COUNT(a.article_id) as article_count
            FROM press p
            LEFT JOIN article a ON p.press_id = a.press_id
            GROUP BY p.press_id, p.press_name
            ORDER BY p.press_name COLLATE "C" {sort_order}
        """
        cur.execute(query)
        return cur.fetchall()


def _fetch_press_stance_distribution(press_id: str) -> Dict[str, int]:
    """Synchronous function to fetch stance distribution for a press."""
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT
                sa.stance_label,
                COUNT(*) as count
            FROM article a
            JOIN stance_analysis sa ON a.article_id = sa.article_id
            WHERE a.press_id = %s
            GROUP BY sa.stance_label
            """,
            (press_id,)
        )
        return {row['stance_label']: row['count'] for row in cur.fetchall()}


def _fetch_press_articles(
    press_id: str,
    sort_order: str,
    limit: int,
    offset: int
) -> Tuple[bool, int, List[Dict[str, Any]]]:
    """Synchronous function to fetch articles by press."""
    with get_db_cursor() as cur:
        # Verify press exists
        cur.execute(
            "SELECT press_id FROM press WHERE press_id = %s",
            (press_id,)
        )
        if not cur.fetchone():
            return False, 0, []

        # Count total articles
        cur.execute(
            """
            SELECT COUNT(*) as total
            FROM article
            WHERE press_id = %s
            """,
            (press_id,)
        )
        result = cur.fetchone()
        total = result['total'] if result else 0

        # Fetch articles
        query = f"""
            SELECT
                a.article_id,
                a.title,
                a.published_at,
                a.img_url,
                p.press_id,
                p.press_name
            FROM article a
            JOIN press p ON a.press_id = p.press_id
            WHERE a.press_id = %s
            ORDER BY a.published_at {sort_order}
            LIMIT %s OFFSET %s
        """
        cur.execute(query, (press_id, limit, offset))
        articles = cur.fetchall()

        return True, total, articles


@router.get(
    "",
    response_model=List[PressDetail],
    status_code=status.HTTP_200_OK,
    summary="Get all press",
    description="Get list of all news organizations",
)
async def get_all_press(
    sort: str = Query("name:asc", description="Sort by: name:asc, name:desc"),
    include: Optional[str] = Query(None, description="Include related data: statistics"),
):
    """
    Get list of all news organizations.

    Args:
        sort: Sort order (name:asc or name:desc)
        include: Include additional data (statistics)

    Returns:
        List of press organizations
    """
    try:
        includes = set(include.split(',')) if include else set()

        # Parse sort parameter
        sort_parts = sort.split(':')
        sort_order = sort_parts[1].upper() if len(sort_parts) > 1 else 'ASC'

        # Run blocking DB query in executor
        press_list = await run_in_executor(_fetch_all_press, sort_order)

        # Build response
        result = []
        for press in press_list:
            # Get stance distribution (if include requested)
            stance_dist = None
            if 'statistics' in includes:
                from src.api.schemas.common import StanceDistribution

                stance_counts = await run_in_executor(
                    _fetch_press_stance_distribution,
                    press['press_id']
                )

                stance_dist = StanceDistribution(
                    support=stance_counts.get('support', 0),
                    neutral=stance_counts.get('neutral', 0),
                    oppose=stance_counts.get('oppose', 0)
                )

            result.append(
                PressDetail(
                    id=press['press_id'],
                    name=press['press_name'],
                    article_count=press['article_count'],
                    stance_distribution=stance_dist,
                )
            )

        return result

    except Exception as e:
        logger.error(f"Error fetching press list: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch press list"
        )


@router.get(
    "/{press_id}/articles",
    response_model=PaginatedResponse[ArticleSummary],
    status_code=status.HTTP_200_OK,
    summary="Get articles by press",
    description="Get list of articles from a specific news organization",
)
async def get_press_articles(
    press_id: str,
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    stance: Optional[StanceType] = Query(None, description="Filter by stance (when model is ready)"),
    sort: str = Query("published_at:desc", description="Sort by: published_at:desc, published_at:asc"),
):
    """
    Get articles from a specific news organization.

    Args:
        press_id: Press ID
        page: Page number
        limit: Items per page
        stance: Filter by stance (not implemented yet)
        sort: Sort order

    Returns:
        Paginated list of articles
    """
    try:
        # Calculate pagination
        offset = (page - 1) * limit

        # Parse sort parameter
        sort_parts = sort.split(':')
        sort_order = sort_parts[1].upper() if len(sort_parts) > 1 else 'DESC'

        # Run blocking DB query in executor
        exists, total, articles = await run_in_executor(
            _fetch_press_articles,
            press_id,
            sort_order,
            limit,
            offset
        )

        if not exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Press {press_id} not found"
            )

        total_pages = math.ceil(total / limit) if total > 0 else 0

        # Build response
        article_list = []
        for article in articles:
            article_list.append(
                ArticleSummary(
                    id=article['article_id'],
                    title=article['title'],
                    press=PressInfo(
                        id=article['press_id'],
                        name=article['press_name']
                    ),
                    published_at=article['published_at'],
                    image_url=article['img_url'],
                    stance=None,  # TODO: when stance model ready
                    similarity_score=None,
                )
            )

        return PaginatedResponse(
            data=article_list,
            pagination=PaginationMeta(
                page=page,
                limit=limit,
                total=total,
                total_pages=total_pages,
            )
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching articles for press {press_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch press articles"
        )
