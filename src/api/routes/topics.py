"""
Topics API endpoints.
"""
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response
from typing import Optional, List, Dict, Any, Tuple
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
    DailyKeywordsResponse,
    KeywordItem,
)
from src.api.utils import run_in_executor
from src.models.database import get_db_cursor

logger = logging.getLogger(__name__)

router = APIRouter()


def _fetch_topics_list(
    target_date: date,
    limit: int,
    offset: int
) -> Tuple[int, List[Dict[str, Any]]]:
    """Synchronous function to fetch topics list."""
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

        # Fetch topics with main article stance
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
                a.img_url as main_article_img_url,
                sa.stance_label as main_article_stance
            FROM topic t
            LEFT JOIN article a ON t.main_article_id = a.article_id
            LEFT JOIN stance_analysis sa ON a.article_id = sa.article_id
            WHERE t.topic_date = %s AND t.is_active = TRUE
            ORDER BY t.topic_rank ASC NULLS LAST, t.cluster_score DESC
            LIMIT %s OFFSET %s
            """,
            (target_date, limit, offset)
        )
        topics = cur.fetchall()

        return total, topics


def _fetch_topic_detail(topic_id: int, includes: set) -> Dict[str, Any]:
    """Synchronous function to fetch topic detail."""
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
            return None

        result = dict(topic)

        # Main article detail (if include requested)
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
                    p.press_name,
                    sa.stance_label
                FROM article a
                JOIN press p ON a.press_id = p.press_id
                LEFT JOIN stance_analysis sa ON a.article_id = sa.article_id
                WHERE a.article_id = %s
                """,
                (topic['main_article_id'],)
            )
            result['main_article_data'] = cur.fetchone()

        return result


def _fetch_topic_articles(
    topic_id: int,
    order_by: str,
    limit: int,
    offset: int
) -> Tuple[bool, int, List[Dict[str, Any]]]:
    """Synchronous function to fetch topic articles."""
    with get_db_cursor() as cur:
        # Verify topic exists
        cur.execute(
            "SELECT topic_id FROM topic WHERE topic_id = %s AND is_active = TRUE",
            (topic_id,)
        )
        if not cur.fetchone():
            return False, 0, []

        # Count total articles
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

        # Fetch articles with stance
        query = f"""
            SELECT
                a.article_id,
                a.title,
                a.published_at,
                a.img_url,
                p.press_id,
                p.press_name,
                tam.similarity_score,
                sa.stance_label
            FROM topic_article_mapping tam
            JOIN article a ON tam.article_id = a.article_id
            JOIN press p ON a.press_id = p.press_id
            LEFT JOIN stance_analysis sa ON a.article_id = sa.article_id
            WHERE tam.topic_id = %s
            ORDER BY {order_by}
            LIMIT %s OFFSET %s
        """
        cur.execute(query, (topic_id, limit, offset))
        articles = cur.fetchall()

        return True, total, articles


def _fetch_visualization_from_db() -> Dict[str, Any]:
    """Synchronous function to fetch visualization from database."""
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT news_date, image_data, dpi, article_count, created_at
            FROM topic_visualization
            WHERE id = 1
            """
        )
        return cur.fetchone()


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

        # Calculate pagination
        offset = (page - 1) * limit

        # Run blocking DB query in executor
        total, topics = await run_in_executor(
            _fetch_topics_list,
            target_date,
            limit,
            offset
        )

        total_pages = math.ceil(total / limit) if total > 0 else 0

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
                    stance=topic.get('main_article_stance'),
                )

            # Stance distribution (if include requested)
            stance_dist = None
            if 'stance_distribution' in includes:
                from src.api.schemas.common import StanceDistribution

                # Count stance distribution for this topic
                cur.execute(
                    """
                    SELECT
                        sa.stance_label,
                        COUNT(*) as count
                    FROM topic_article_mapping tam
                    JOIN stance_analysis sa ON tam.article_id = sa.article_id
                    WHERE tam.topic_id = %s
                    GROUP BY sa.stance_label
                    """,
                    (topic['topic_id'],)
                )
                stance_counts = {row['stance_label']: row['count'] for row in cur.fetchall()}

                stance_dist = StanceDistribution(
                    support=stance_counts.get('support', 0),
                    neutral=stance_counts.get('neutral', 0),
                    oppose=stance_counts.get('oppose', 0)
                )

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
    "/visualization",
    response_class=Response,
    status_code=status.HTTP_200_OK,
    summary="Get topic visualization",
    description="Get pre-generated DataMapPlot visualization of BERTopic clustering",
    responses={
        200: {
            "content": {"image/png": {}},
            "description": "PNG image of topic clustering visualization"
        },
        404: {"description": "No visualization available"},
        500: {"description": "Internal server error"}
    }
)
async def get_topic_visualization():
    """
    Get pre-generated DataMapPlot visualization of topic clustering.

    This endpoint returns the visualization image that was generated during
    the hourly pipeline (after BERTopic clustering).

    Returns:
        PNG image with Content-Type: image/png and 1-hour cache control

    Note:
        - Returns pre-generated image (fast response)
        - Generated automatically every hour after BERTopic clustering
        - Returns 404 if no visualization has been generated yet
    """
    try:
        # Fetch visualization from DB
        result = await run_in_executor(_fetch_visualization_from_db)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No visualization available. It will be generated after the next pipeline run."
            )

        image_data = result['image_data']
        news_date = result['news_date']

        # Handle memoryview type (psycopg2 returns BYTEA as memoryview)
        if isinstance(image_data, memoryview):
            image_data = bytes(image_data)

        logger.info(f"Returning visualization for {news_date} ({len(image_data)} bytes)")

        # Return image with cache control headers
        return Response(
            content=image_data,
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
                "Content-Disposition": f'inline; filename="topic_visualization_{news_date}.png"'
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching visualization: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch visualization"
        )

@router.get("/daily-keywords", response_model=DailyKeywordsResponse)
async def get_daily_keywords(
    date: Optional[str] = Query(None, description="News date (YYYY-MM-DD). Default: today"),
    limit: int = Query(50, ge=10, le=100, description="Maximum number of keywords (10-100)")
):
    """
    Get daily political keywords aggregated from all topics (for word cloud).

    This endpoint aggregates keywords from all topics for a specific date,
    combining their scores to produce a weighted keyword list suitable for
    word cloud visualization.

    Args:
        date: Target date (YYYY-MM-DD). Default: today
        limit: Maximum number of keywords to return (10-100, default: 50)

    Returns:
        DailyKeywordsResponse with keywords and weights

    Example:
        GET /api/topics/daily-keywords?date=2025-11-28&limit=50
    """
    try:
        # Parse date
        if date:
            try:
                target_date = datetime.strptime(date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid date format. Use YYYY-MM-DD"
                )
        else:
            target_date = datetime.now().date()

        # Fetch keywords from DB
        total_topics, keyword_freq = await run_in_executor(
            _fetch_daily_keywords,
            target_date,
            limit
        )

        # Build response
        keywords = [
            KeywordItem(text=kw, weight=round(freq, 2))
            for kw, freq in keyword_freq.items()
        ]

        return DailyKeywordsResponse(
            date=str(target_date),
            total_topics=total_topics,
            keywords=keywords
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching daily keywords: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch daily keywords"
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

        # Run blocking DB query in executor
        topic_data = await run_in_executor(
            _fetch_topic_detail,
            topic_id,
            includes
        )

        if not topic_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Topic {topic_id} not found"
            )

        # Main article detail (if include requested)
        main_article = None
        if 'main_article' in includes and topic_data.get('main_article_data'):
            article_data = topic_data['main_article_data']
            from src.api.schemas import ArticleDetail, TopicBrief
            from src.api.schemas.common import StanceData, StanceProbabilities

            # Get stance data
            stance = None
            if article_data.get('stance_label'):
                stance = StanceData(
                    label=article_data['stance_label'],
                    score=0.0,  # Unknown without full data
                    probabilities=StanceProbabilities(
                        support=0.33,
                        neutral=0.33,
                        oppose=0.33
                    )
                )

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
                    id=topic_data['topic_id'],
                    name=topic_data['topic_title']
                ),
                stance=stance,
            )

        # Stance distribution (if include requested)
        stance_dist = None
        if 'stance_distribution' in includes:
            from src.api.schemas.common import StanceDistribution

            # Count stance distribution for this topic
            with get_db_cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        sa.stance_label,
                        COUNT(*) as count
                    FROM topic_article_mapping tam
                    JOIN stance_analysis sa ON tam.article_id = sa.article_id
                    WHERE tam.topic_id = %s
                    GROUP BY sa.stance_label
                    """,
                    (topic_id,)
                )
                stance_counts = {row['stance_label']: row['count'] for row in cur.fetchall()}

                stance_dist = StanceDistribution(
                    support=stance_counts.get('support', 0),
                    neutral=stance_counts.get('neutral', 0),
                    oppose=stance_counts.get('oppose', 0)
                )

        # Keywords (if include requested)
        keywords = []
        if 'keywords' in includes:
            # Extract from topic_title (simple split for now)
            keywords = topic_data['topic_title'].split()[:5]

        return TopicDetail(
            id=topic_data['topic_id'],
            name=topic_data['topic_title'],
            description=None,  # Not stored yet
            article_count=topic_data['article_count'],
            topic_date=topic_data['topic_date'],
            topic_rank=topic_data['topic_rank'],
            cluster_score=float(topic_data['cluster_score']),
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
        # Calculate pagination
        offset = (page - 1) * limit

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

        # Run blocking DB query in executor
        exists, total, articles = await run_in_executor(
            _fetch_topic_articles,
            topic_id,
            order_by,
            limit,
            offset
        )

        if not exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Topic {topic_id} not found"
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


# ========================================
# Daily Keywords API (Word Cloud)
# ========================================

def _fetch_daily_keywords(target_date: date, limit: int) -> Tuple[int, Dict[str, float]]:
    """
    Synchronous function to fetch and aggregate daily keywords.

    Returns:
        Tuple of (total_topics, keyword_freq_dict)
    """
    with get_db_cursor() as cur:
        # Fetch all topics with keywords for the date
        cur.execute(
            """
            SELECT keywords
            FROM topic
            WHERE topic_date = %s
              AND is_active = TRUE
              AND keywords IS NOT NULL
            """,
            (target_date,)
        )

        rows = cur.fetchall()
        total_topics = len(rows)

        # Aggregate keyword frequencies
        keyword_freq = {}
        for row in rows:
            keywords = row['keywords']  # JSONB already parsed
            if not keywords:
                continue

            for kw in keywords:
                keyword = kw['keyword']
                score = kw['score']

                if keyword in keyword_freq:
                    keyword_freq[keyword] += score
                else:
                    keyword_freq[keyword] = score

        # Sort by frequency and limit
        sorted_keywords = sorted(
            keyword_freq.items(),
            key=lambda x: x[1],
            reverse=True
        )[:limit]

        # Convert to dict
        result_dict = {kw: freq for kw, freq in sorted_keywords}

        return total_topics, result_dict


