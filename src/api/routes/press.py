"""
Press (news organizations) API endpoints.
"""
from fastapi import APIRouter, HTTPException, Query, status
from typing import Optional, List
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
from src.models.database import get_db_cursor

logger = logging.getLogger(__name__)

router = APIRouter()


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

        with get_db_cursor() as cur:
            # Fetch all press
            query = f"""
                SELECT
                    p.press_id,
                    p.press_name
                FROM press p
                ORDER BY p.press_name {sort_order}
            """
            cur.execute(query)
            press_list = cur.fetchall()

            # Build response
            result = []
            for press in press_list:
                # Get article count
                cur.execute(
                    "SELECT COUNT(*) as count FROM article WHERE press_id = %s",
                    (press['press_id'],)
                )
                count_result = cur.fetchone()
                article_count = count_result['count'] if count_result else 0

                # Get stance distribution (if include requested)
                stance_dist = None
                if 'statistics' in includes:
                    # TODO: Calculate from stance_analysis table when model is ready
                    pass

                result.append(
                    PressDetail(
                        id=press['press_id'],
                        name=press['press_name'],
                        article_count=article_count,
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
        with get_db_cursor() as cur:
            # Verify press exists
            cur.execute(
                "SELECT press_id FROM press WHERE press_id = %s",
                (press_id,)
            )
            if not cur.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Press {press_id} not found"
                )

            # Count total articles
            # Note: stance filter not implemented yet
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

            # Calculate pagination
            offset = (page - 1) * limit
            total_pages = math.ceil(total / limit) if total > 0 else 0

            # Parse sort parameter
            sort_parts = sort.split(':')
            sort_order = sort_parts[1].upper() if len(sort_parts) > 1 else 'DESC'

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
