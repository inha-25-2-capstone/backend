"""
Articles API endpoints.
"""
from fastapi import APIRouter, HTTPException, Query, status
from typing import Optional
from datetime import date
import logging
import math

from src.api.schemas import (
    ArticleSummary,
    ArticleDetail,
    PaginatedResponse,
    PaginationMeta,
    PressInfo,
    TopicBrief,
    StanceType,
)
from src.models.database import get_db_cursor

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "",
    response_model=PaginatedResponse[ArticleSummary],
    status_code=status.HTTP_200_OK,
    summary="Get all articles",
    description="Get list of all articles with optional filters",
)
async def get_articles(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    press_id: Optional[str] = Query(None, description="Filter by press ID"),
    topic_id: Optional[int] = Query(None, description="Filter by topic ID"),
    stance: Optional[StanceType] = Query(None, description="Filter by stance (when model is ready)"),
    start_date: Optional[date] = Query(None, description="Filter by start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="Filter by end date (YYYY-MM-DD)"),
    sort: str = Query("published_at:desc", description="Sort by: published_at:desc, published_at:asc"),
):
    """
    Get list of all articles with optional filtering.

    Args:
        page: Page number (1-indexed)
        limit: Items per page
        press_id: Filter by press ID
        topic_id: Filter by topic ID
        stance: Filter by stance (not implemented yet)
        start_date: Start date filter
        end_date: End date filter
        sort: Sort order

    Returns:
        Paginated list of articles
    """
    try:
        # Build WHERE clause
        where_conditions = []
        params = []

        if press_id:
            where_conditions.append("a.press_id = %s")
            params.append(press_id)

        if topic_id:
            where_conditions.append(
                "EXISTS (SELECT 1 FROM topic_article_mapping tam WHERE tam.article_id = a.article_id AND tam.topic_id = %s)"
            )
            params.append(topic_id)

        if start_date:
            where_conditions.append("a.published_at >= %s")
            params.append(start_date)

        if end_date:
            where_conditions.append("a.published_at <= %s")
            params.append(end_date)

        # Note: stance filter not implemented yet (stance_analysis table empty)

        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

        with get_db_cursor() as cur:
            # Count total articles
            count_query = f"""
                SELECT COUNT(*) as total
                FROM article a
                WHERE {where_clause}
            """
            cur.execute(count_query, params)
            result = cur.fetchone()
            total = result['total'] if result else 0

            # Calculate pagination
            offset = (page - 1) * limit
            total_pages = math.ceil(total / limit) if total > 0 else 0

            # Parse sort parameter
            sort_parts = sort.split(':')
            sort_field = sort_parts[0] if len(sort_parts) > 0 else 'published_at'
            sort_order = sort_parts[1].upper() if len(sort_parts) > 1 else 'DESC'

            # Map sort field
            if sort_field == 'published_at':
                order_by = f"a.published_at {sort_order}"
            else:
                order_by = "a.published_at DESC"

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
                WHERE {where_clause}
                ORDER BY {order_by}
                LIMIT %s OFFSET %s
            """

            cur.execute(query, params + [limit, offset])
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

    except Exception as e:
        logger.error(f"Error fetching articles: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch articles"
        )


@router.get(
    "/{article_id}",
    response_model=ArticleDetail,
    status_code=status.HTTP_200_OK,
    summary="Get article detail",
    description="Get detailed information about a specific article",
)
async def get_article_detail(
    article_id: int,
    include: Optional[str] = Query(
        None,
        description="Include related data: stance,topic,related_articles"
    ),
):
    """
    Get detailed information about a specific article.

    Args:
        article_id: Article ID
        include: Comma-separated list of related data to include

    Returns:
        Detailed article information
    """
    try:
        includes = set(include.split(',')) if include else set()

        with get_db_cursor() as cur:
            # Fetch article
            cur.execute(
                """
                SELECT
                    a.article_id,
                    a.title,
                    a.content,
                    a.summary,
                    a.img_url,
                    a.article_url,
                    a.published_at,
                    a.author,
                    p.press_id,
                    p.press_name
                FROM article a
                JOIN press p ON a.press_id = p.press_id
                WHERE a.article_id = %s
                """,
                (article_id,)
            )
            article = cur.fetchone()

            if not article:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Article {article_id} not found"
                )

            # Get topic (if article belongs to one)
            topic = None
            if 'topic' in includes:
                cur.execute(
                    """
                    SELECT t.topic_id, t.topic_title
                    FROM topic t
                    JOIN topic_article_mapping tam ON t.topic_id = tam.topic_id
                    WHERE tam.article_id = %s AND t.is_active = TRUE
                    LIMIT 1
                    """,
                    (article_id,)
                )
                topic_data = cur.fetchone()
                if topic_data:
                    topic = TopicBrief(
                        id=topic_data['topic_id'],
                        name=topic_data['topic_title']
                    )

            # Get stance (if include requested)
            stance = None
            if 'stance' in includes:
                # TODO: Query stance_analysis table when model is ready
                pass

            # Get related articles (if include requested)
            # Note: Not implemented in this phase
            # Can be based on same topic or embedding similarity

            return ArticleDetail(
                id=article['article_id'],
                title=article['title'],
                content=article['content'],
                summary=article['summary'],
                image_url=article['img_url'],
                original_url=article['article_url'],
                published_at=article['published_at'],
                author=article['author'],
                press=PressInfo(
                    id=article['press_id'],
                    name=article['press_name']
                ),
                topic=topic,
                stance=stance,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching article {article_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch article details"
        )
