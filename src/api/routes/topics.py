"""
Topics API endpoints.
"""
from fastapi import APIRouter, HTTPException, Query, status
from typing import Optional, List
from datetime import datetime, date
import logging
import math

from src.api.schemas import (
    TopicSummary,
    TopicDetail,
    ArticleSummary,
    PaginatedResponse,
    PaginationParams,
    PaginationMeta,
    PressInfo,
    MainArticleInfo,
    StanceDistribution,
    StanceType,
)
from src.models.database import get_db_cursor

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "",
    response_model=PaginatedResponse[TopicSummary],
    status_code=status.HTTP_200_OK,
    summary="Get topic list",
    description="Get list of topics, optionally filtered by date. Default returns today's top 7 topics.",
)
async def get_topics(
    date_filter: Optional[date] = Query(None, alias="date", description="Filter by date (YYYY-MM-DD)"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(7, ge=1, le=100, description="Items per page"),
    include: Optional[str] = Query(None, description="Include related data: main_article,stance_distribution"),
):
    """
    Get list of topics.

    Args:
        date_filter: Filter by specific date (default: today)
        page: Page number (1-indexed)
        limit: Items per page (default 7 for main page)
        include: Comma-separated list of related data to include

    Returns:
        Paginated list of topics
    """
    try:
        # Parse include parameter
        includes = set(include.split(',')) if include else set()

        # Use today's date if not specified
        target_date = date_filter or datetime.utcnow().date()

        with get_db_cursor() as cur:
            # Count total topics for this date
            cur.execute(
                """
                SELECT COUNT(*) as total
                FROM topic
                WHERE topic_date = %s AND is_active = TRUE
                """,
                (target_date,)
            )
            result = cur.fetchone()
            total = result['total'] if result else 0

            # Calculate pagination
            offset = (page - 1) * limit
            total_pages = math.ceil(total / limit) if total > 0 else 0

            # Fetch topics
            cur.execute(
                """
                SELECT
                    t.topic_id,
                    t.topic_title,
                    t.topic_rank,
                    t.cluster_score,
                    t.article_count,
                    t.topic_date,
                    t.main_article_id,
                    a.title as main_article_title,
                    a.img_url as main_article_img_url
                FROM topic t
                LEFT JOIN article a ON t.main_article_id = a.article_id
                WHERE t.topic_date = %s AND t.is_active = TRUE
                ORDER BY COALESCE(t.topic_rank, 999), t.article_count DESC
                LIMIT %s OFFSET %s
                """,
                (target_date, limit, offset)
            )
            topics = cur.fetchall()

            # Build response
            topic_list = []
            for topic in topics:
                # Main article info (if include requested)
                main_article = None
                if 'main_article' in includes and topic['main_article_id']:
                    main_article = MainArticleInfo(
                        id=topic['main_article_id'],
                        title=topic['main_article_title'],
                        image_url=topic['main_article_img_url'],
                        stance=None,  # TODO: when stance model ready
                    )

                # Stance distribution (if include requested)
                stance_dist = None
                if 'stance_distribution' in includes:
                    # TODO: Calculate from stance_analysis table when model is ready
                    # For now, return None
                    pass

                topic_list.append(
                    TopicSummary(
                        id=topic['topic_id'],
                        name=topic['topic_title'],
                        description=None,  # Not stored in DB yet
                        article_count=topic['article_count'],
                        topic_rank=topic['topic_rank'] or 1,
                        cluster_score=float(topic['cluster_score']) if topic['cluster_score'] else 0.0,
                        topic_date=topic['topic_date'],
                        main_article=main_article,
                        stance_distribution=stance_dist,
                    )
                )

            return PaginatedResponse(
                data=topic_list,
                pagination=PaginationMeta(
                    page=page,
                    limit=limit,
                    total=total,
                    total_pages=total_pages,
                )
            )

    except Exception as e:
        logger.error(f"Error fetching topics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch topics"
        )


@router.get(
    "/{topic_id}",
    response_model=TopicDetail,
    status_code=status.HTTP_200_OK,
    summary="Get topic detail",
    description="Get detailed information about a specific topic",
)
async def get_topic_detail(
    topic_id: int,
    include: Optional[str] = Query(
        None,
        description="Include related data: main_article,stance_distribution,keywords"
    ),
):
    """
    Get detailed information about a specific topic.

    Args:
        topic_id: Topic ID
        include: Comma-separated list of related data to include

    Returns:
        Detailed topic information
    """
    try:
        includes = set(include.split(',')) if include else set()

        with get_db_cursor() as cur:
            # Fetch topic
            cur.execute(
                """
                SELECT
                    t.topic_id,
                    t.topic_title,
                    t.topic_rank,
                    t.cluster_score,
                    t.article_count,
                    t.topic_date,
                    t.main_article_id
                FROM topic t
                WHERE t.topic_id = %s AND t.is_active = TRUE
                """,
                (topic_id,)
            )
            topic = cur.fetchone()

            if not topic:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Topic {topic_id} not found"
                )

            # Main article detail (if include requested)
            main_article = None
            if 'main_article' in includes and topic['main_article_id']:
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
                    (topic['main_article_id'],)
                )
                article_data = cur.fetchone()

                if article_data:
                    from src.api.schemas import ArticleDetail, TopicBrief

                    main_article = ArticleDetail(
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
                        topic=TopicBrief(
                            id=topic['topic_id'],
                            name=topic['topic_title']
                        ),
                        stance=None,  # TODO: when stance model ready
                    )

            # Stance distribution (if include requested)
            stance_dist = None
            if 'stance_distribution' in includes:
                # TODO: Calculate from stance_analysis table when model is ready
                pass

            # Keywords (if include requested)
            keywords = []
            if 'keywords' in includes:
                # Extract from topic_title (simple split for now)
                keywords = topic['topic_title'].split()[:5]

            return TopicDetail(
                id=topic['topic_id'],
                name=topic['topic_title'],
                description=None,  # Not stored yet
                article_count=topic['article_count'],
                topic_date=topic['topic_date'],
                topic_rank=topic['topic_rank'],
                cluster_score=float(topic['cluster_score']),
                main_article=main_article,
                stance_distribution=stance_dist,
                keywords=keywords,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching topic {topic_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch topic details"
        )


@router.get(
    "/{topic_id}/articles",
    response_model=PaginatedResponse[ArticleSummary],
    status_code=status.HTTP_200_OK,
    summary="Get articles by topic",
    description="Get list of articles belonging to a specific topic",
)
async def get_topic_articles(
    topic_id: int,
    stance: Optional[StanceType] = Query(None, description="Filter by stance"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    sort: str = Query("similarity:desc", description="Sort by: similarity:desc, published_at:desc"),
):
    """
    Get articles belonging to a specific topic.

    Args:
        topic_id: Topic ID
        stance: Filter by stance (support/neutral/oppose) - when model is ready
        page: Page number
        limit: Items per page
        sort: Sort order

    Returns:
        Paginated list of articles
    """
    try:
        with get_db_cursor() as cur:
            # Verify topic exists
            cur.execute(
                "SELECT topic_id FROM topic WHERE topic_id = %s AND is_active = TRUE",
                (topic_id,)
            )
            if not cur.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Topic {topic_id} not found"
                )

            # Count total articles
            # Note: stance filter not implemented yet (stance_analysis table empty)
            cur.execute(
                """
                SELECT COUNT(*) as total
                FROM topic_article_mapping tam
                WHERE tam.topic_id = %s
                """,
                (topic_id,)
            )
            result = cur.fetchone()
            total = result['total'] if result else 0

            # Calculate pagination
            offset = (page - 1) * limit
            total_pages = math.ceil(total / limit) if total > 0 else 0

            # Parse sort parameter
            sort_parts = sort.split(':')
            sort_field = sort_parts[0] if len(sort_parts) > 0 else 'similarity'
            sort_order = sort_parts[1].upper() if len(sort_parts) > 1 else 'DESC'

            # Map sort field
            if sort_field == 'similarity':
                order_by = f"tam.similarity_score {sort_order}"
            elif sort_field == 'published_at':
                order_by = f"a.published_at {sort_order}"
            else:
                order_by = "tam.similarity_score DESC"

            # Fetch articles
            query = f"""
                SELECT
                    a.article_id,
                    a.title,
                    a.published_at,
                    a.img_url,
                    p.press_id,
                    p.press_name,
                    tam.similarity_score
                FROM topic_article_mapping tam
                JOIN article a ON tam.article_id = a.article_id
                JOIN press p ON a.press_id = p.press_id
                WHERE tam.topic_id = %s
                ORDER BY {order_by}
                LIMIT %s OFFSET %s
            """

            cur.execute(query, (topic_id, limit, offset))
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
                        similarity_score=float(article['similarity_score']) if article['similarity_score'] else None,
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
        logger.error(f"Error fetching articles for topic {topic_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch topic articles"
        )
