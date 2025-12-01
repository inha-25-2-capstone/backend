"""
Articles API endpoints.
"""
from fastapi import APIRouter, HTTPException, Query, status
from typing import Optional, Dict, Any, List, Tuple
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
from src.api.utils import run_in_executor
from src.models.database import get_db_cursor

logger = logging.getLogger(__name__)

router = APIRouter()


def _fetch_articles_list(
    where_clause: str,
    params: List,
    order_by: str,
    limit: int,
    offset: int
) -> Tuple[int, List[Dict[str, Any]]]:
    """Synchronous function to fetch articles list."""
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

        # Fetch articles
        query = f"""
            SELECT
                a.article_id,
                a.title,
                a.published_at,
                a.img_url,
                p.press_id,
                p.press_name,
                sa.stance_label,
                tam.similarity_score
            FROM article a
            JOIN press p ON a.press_id = p.press_id
            LEFT JOIN stance_analysis sa ON a.article_id = sa.article_id
            LEFT JOIN LATERAL (
                SELECT similarity_score
                FROM topic_article_mapping
                WHERE article_id = a.article_id
                ORDER BY similarity_score DESC
                LIMIT 1
            ) tam ON true
            WHERE {where_clause}
            ORDER BY {order_by}
            LIMIT %s OFFSET %s
        """
        cur.execute(query, params + [limit, offset])
        articles = cur.fetchall()

        return total, articles


def _fetch_article_detail(article_id: int, includes: set) -> Dict[str, Any]:
    """Synchronous function to fetch article detail."""
    with get_db_cursor() as cur:
        # Fetch article with basic stance info
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
                p.press_name,
                sa.stance_label
            FROM article a
            JOIN press p ON a.press_id = p.press_id
            LEFT JOIN stance_analysis sa ON a.article_id = sa.article_id
            WHERE a.article_id = %s
            """,
            (article_id,)
        )
        article = cur.fetchone()

        if not article:
            return None

        result = dict(article)

        # Get topic (if requested)
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
            result['topic_data'] = topic_data

        return result


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
    stance: Optional[StanceType] = Query(None, description="Filter by stance (support/neutral/oppose)"),
    has_stance: Optional[bool] = Query(None, description="Filter by stance presence (true: has stance, false: no stance)"),
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

        # Stance filters
        if stance:
            where_conditions.append(
                "EXISTS (SELECT 1 FROM stance_analysis sa WHERE sa.article_id = a.article_id AND sa.stance_label = %s)"
            )
            params.append(stance.value)

        if has_stance is not None:
            if has_stance:
                # Only articles WITH stance
                where_conditions.append(
                    "EXISTS (SELECT 1 FROM stance_analysis sa WHERE sa.article_id = a.article_id)"
                )
            else:
                # Only articles WITHOUT stance
                where_conditions.append(
                    "NOT EXISTS (SELECT 1 FROM stance_analysis sa WHERE sa.article_id = a.article_id)"
                )

        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

        # Calculate pagination
        offset = (page - 1) * limit

        # Parse sort parameter
        sort_parts = sort.split(':')
        sort_field = sort_parts[0] if len(sort_parts) > 0 else 'published_at'
        sort_order = sort_parts[1].upper() if len(sort_parts) > 1 else 'DESC'

        # Map sort field
        if sort_field == 'published_at':
            order_by = f"a.published_at {sort_order}"
        else:
            order_by = "a.published_at DESC"

        # Run blocking DB query in executor
        total, articles = await run_in_executor(
            _fetch_articles_list,
            where_clause,
            params,
            order_by,
            limit,
            offset
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
                    stance=article.get('stance_label'),
                    similarity_score=float(article['similarity_score']) if article.get('similarity_score') else None,
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

        # Run blocking DB query in executor
        article_data = await run_in_executor(
            _fetch_article_detail,
            article_id,
            includes
        )

        if not article_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Article {article_id} not found"
            )

        # Get topic (if requested)
        topic = None
        if 'topic' in includes and article_data.get('topic_data'):
            topic_info = article_data['topic_data']
            topic = TopicBrief(
                id=topic_info['topic_id'],
                name=topic_info['topic_title']
            )

        # Get stance
        stance = None
        if article_data.get('stance_label'):
            # Basic stance from article query (always included)
            if 'stance' in includes:
                # Full stance data with probabilities
                from src.models.database import StanceRepository
                from src.api.schemas.common import StanceData, StanceProbabilities

                stance_data = await run_in_executor(
                    StanceRepository.get_by_article_id,
                    article_id
                )

                if stance_data:
                    stance = StanceData(
                        label=stance_data['stance_label'],
                        score=float(stance_data['stance_score']),
                        probabilities=StanceProbabilities(
                            support=float(stance_data['prob_positive']),
                            neutral=float(stance_data['prob_neutral']),
                            oppose=float(stance_data['prob_negative'])
                        )
                    )
            else:
                # Simple stance data without detailed probabilities (default 0.33 for unknown)
                from src.api.schemas.common import StanceData, StanceProbabilities

                stance = StanceData(
                    label=article_data['stance_label'],
                    score=0.0,  # Unknown without full data
                    probabilities=StanceProbabilities(
                        support=0.33,
                        neutral=0.33,
                        oppose=0.33
                    )
                )

        return ArticleDetail(
            id=article_data['article_id'],
            title=article_data['title'],
            content=article_data['content'],
            summary=article_data['summary'],
            image_url=article_data['img_url'],
            original_url=article_data['article_url'],
            published_at=article_data['published_at'],
            author=article_data['author'],
            press=PressInfo(
                id=article_data['press_id'],
                name=article_data['press_name']
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
