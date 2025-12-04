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
    PressStanceDistributionResponse,
    PressStanceInfo,
    TopicStanceInfo,
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

        # Fetch articles with stance and similarity
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
            WHERE a.press_id = %s
            ORDER BY a.published_at {sort_order}
            LIMIT %s OFFSET %s
        """
        cur.execute(query, (press_id, limit, offset))
        articles = cur.fetchall()

        return True, total, articles


def _fetch_press_topic_stance_distribution(
    news_date,
    topic_limit: int
) -> Dict[str, Any]:
    """
    Synchronous function to fetch press stance distribution across topics.

    Args:
        news_date: date object or string (YYYY-MM-DD)
        topic_limit: Maximum number of topics

    Returns press-topic-stance data for building the distribution.
    """
    with get_db_cursor() as cur:
        # Get top topics for the given date
        cur.execute(
            """
            SELECT topic_id, topic_title
            FROM topic
            WHERE topic_date = %s
            AND topic_rank IS NOT NULL
            ORDER BY topic_rank ASC
            LIMIT %s
            """,
            (news_date, topic_limit)
        )
        topics = cur.fetchall()

        if not topics:
            return {
                'topics': [],
                'press_list': [],
                'stance_data': [],
                'topic_names': {}
            }

        topic_ids = [t['topic_id'] for t in topics]
        topic_names = {t['topic_id']: t['topic_title'] for t in topics}

        # Get all press
        cur.execute("SELECT press_id, press_name FROM press ORDER BY press_name")
        press_list = cur.fetchall()

        # Get stance distribution for each press-topic combination
        cur.execute(
            """
            SELECT
                a.press_id,
                tam.topic_id,
                sa.stance_label,
                COUNT(*) as count
            FROM article a
            JOIN topic_article_mapping tam ON a.article_id = tam.article_id
            JOIN stance_analysis sa ON a.article_id = sa.article_id
            WHERE tam.topic_id = ANY(%s)
            GROUP BY a.press_id, tam.topic_id, sa.stance_label
            ORDER BY a.press_id, tam.topic_id, sa.stance_label
            """,
            (topic_ids,)
        )
        stance_data = cur.fetchall()

        # Build result structure
        result = {
            'topics': topics,
            'press_list': press_list,
            'stance_data': stance_data,
            'topic_names': topic_names
        }

        return result


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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching articles for press {press_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch press articles"
        )


@router.get(
    "/stance-distribution",
    response_model=PressStanceDistributionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get press stance distribution across topics",
    description="Get stance distribution for each press organization across major topics",
)
async def get_press_stance_distribution(
    date: Optional[str] = Query(None, description="News date (YYYY-MM-DD), default: today"),
    limit: int = Query(10, ge=1, le=20, description="Max number of topics to analyze"),
):
    """
    Get stance distribution for each press organization across major topics.

    Shows which stance (support/neutral/oppose) each press organization uses most
    for each major topic of the day.

    Args:
        date: News date (YYYY-MM-DD), defaults to today
        limit: Maximum number of topics to analyze (1-20, default: 10)

    Returns:
        Press stance distribution across topics
    """
    try:
        from datetime import datetime, timezone, timedelta

        # Parse date or use today
        if date:
            try:
                news_date = datetime.strptime(date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid date format. Use YYYY-MM-DD"
                )
        else:
            # Use today's date in KST
            kst = timezone(timedelta(hours=9))
            now_kst = datetime.now(kst)
            # If before 5 AM, use previous day
            if now_kst.hour < 5:
                news_date = (now_kst - timedelta(days=1)).date()
            else:
                news_date = now_kst.date()

        news_date_str = news_date.strftime("%Y-%m-%d")

        # Run blocking DB query in executor (pass date object, not string)
        data = await run_in_executor(
            _fetch_press_topic_stance_distribution,
            news_date,
            limit
        )

        # Check if we have topics
        if not data or not data.get('topics'):
            # No topics found for this date
            return PressStanceDistributionResponse(
                date=news_date_str,
                total_topics=0,
                press_list=[]
            )

        # Build response structure
        topics = data['topics']
        press_list = data['press_list']
        stance_data = data['stance_data']
        topic_names = data['topic_names']

        # Organize stance data by press and topic
        # press_id -> topic_id -> stance_label -> count
        press_topic_stance = {}
        for row in stance_data:
            press_id = row['press_id']
            topic_id = row['topic_id']
            stance_label = row['stance_label']
            count = row['count']

            if press_id not in press_topic_stance:
                press_topic_stance[press_id] = {}
            if topic_id not in press_topic_stance[press_id]:
                press_topic_stance[press_id][topic_id] = {
                    'support': 0,
                    'neutral': 0,
                    'oppose': 0
                }

            press_topic_stance[press_id][topic_id][stance_label] = count

        # Build final response
        press_response_list = []
        for press in press_list:
            press_id = press['press_id']
            press_name = press['press_name']

            # Get stance info for each topic
            topic_stances = []
            if press_id in press_topic_stance:
                for topic in topics:
                    topic_id = topic['topic_id']
                    topic_name = topic['topic_title']

                    if topic_id in press_topic_stance[press_id]:
                        distribution = press_topic_stance[press_id][topic_id]

                        # Determine dominant stance
                        max_count = max(distribution.values())
                        if max_count == 0:
                            continue  # Skip if no articles

                        # Find stance with max count (prefer support > neutral > oppose in case of tie)
                        if distribution['support'] == max_count:
                            dominant = 'support'
                        elif distribution['neutral'] == max_count:
                            dominant = 'neutral'
                        else:
                            dominant = 'oppose'

                        topic_stances.append(
                            TopicStanceInfo(
                                topic_id=topic_id,
                                topic_name=topic_name,
                                dominant_stance=dominant,
                                distribution=StanceDistribution(
                                    support=distribution['support'],
                                    neutral=distribution['neutral'],
                                    oppose=distribution['oppose']
                                )
                            )
                        )

            # Only add press if they have at least one topic
            if topic_stances:
                press_response_list.append(
                    PressStanceInfo(
                        press_id=press_id,
                        press_name=press_name,
                        topic_stances=topic_stances
                    )
                )

        return PressStanceDistributionResponse(
            date=news_date_str,
            total_topics=len(topics),
            press_list=press_response_list
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching press stance distribution: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch press stance distribution"
        )
