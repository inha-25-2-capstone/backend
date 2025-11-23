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
)
from src.api.utils import run_in_executor
from src.models.database import get_db_cursor
from src.services.bertopic_service import fetch_articles_with_embeddings
from src.services.ai_client import create_ai_client
import os

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
                    p.press_name
                FROM article a
                JOIN press p ON a.press_id = p.press_id
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

        return True, total, articles


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
    "/visualization",
    response_class=Response,
    status_code=status.HTTP_200_OK,
    summary="Get topic visualization",
    description="Generate DataMapPlot visualization of BERTopic clustering",
    responses={
        200: {
            "content": {"image/png": {}},
            "description": "PNG image of topic clustering visualization"
        },
        400: {"description": "Bad request (not enough data)"},
        500: {"description": "Internal server error"}
    }
)
async def get_topic_visualization(
    date_filter: Optional[date] = Query(None, alias="date", description="Filter by date (YYYY-MM-DD)"),
    limit: int = Query(200, ge=10, le=1000, description="Number of articles to visualize"),
    dpi: int = Query(150, ge=50, le=300, description="Image resolution (DPI)"),
):
    """
    Generate and return DataMapPlot visualization of topic clustering.

    This endpoint runs BERTopic clustering on articles from the database and
    generates a DataMapPlot visualization showing how articles are clustered
    into topics.

    Args:
        date_filter: Filter articles by specific date (default: today)
        limit: Maximum number of articles to visualize (default: 200)
        dpi: Image resolution in DPI (default: 150)

    Returns:
        PNG image with Content-Type: image/png and 1-hour cache control

    Note:
        - Generates visualization on-the-fly (may take 10-30 seconds)
        - Cached for 1 hour to improve performance
        - Requires at least 5 articles with embeddings
    """
    try:
        logger.info(f"Generating visualization (date={date_filter}, limit={limit})")

        # Fetch articles with embeddings from DB (run in executor)
        articles, embeddings, doc_texts = await run_in_executor(
            fetch_articles_with_embeddings,
            date_filter,
            limit
        )

        if not articles or embeddings is None:
            raise ValueError("No articles with embeddings found")

        if len(articles) < 5:
            raise ValueError(f"Not enough articles for visualization ({len(articles)} < 5)")

        logger.info(f"Sending {len(articles)} articles to HF Spaces for visualization")

        # Get AI service configuration
        AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "https://gaaahee-news-stance-detection.hf.space")
        AI_SERVICE_TIMEOUT = int(os.getenv("AI_SERVICE_TIMEOUT", "240"))

        # Call HF Spaces visualization API
        with create_ai_client(base_url=AI_SERVICE_URL, timeout=AI_SERVICE_TIMEOUT) as ai_client:
            image_bytes = ai_client.generate_topic_visualization(
                embeddings=embeddings.tolist(),
                texts=doc_texts,
                news_date=str(date_filter or datetime.now().date()),
                dpi=dpi,
                width=1400,
                height=1400
            )

        # Return image with cache control headers
        return Response(
            content=image_bytes,
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
                "Content-Disposition": f'inline; filename="topic_visualization_{date_filter or "latest"}.png"'
            }
        )

    except ValueError as e:
        # Not enough data for visualization
        logger.warning(f"Visualization failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error generating visualization: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate visualization"
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


