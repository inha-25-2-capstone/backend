"""
API response schemas.
"""
from typing import Optional, List
from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime

from .common import StanceType, StanceData, StanceDistribution


# ========================================
# Press Schemas
# ========================================

class PressInfo(BaseModel):
    """Press (news organization) information."""
    id: str = Field(description="Press ID (Naver press code)")
    name: str = Field(description="Press name")

    class Config:
        from_attributes = True


class PressDetail(BaseModel):
    """Detailed press information with statistics."""
    id: str = Field(description="Press ID")
    name: str = Field(description="Press name")
    article_count: int = Field(ge=0, description="Total number of articles")
    stance_distribution: Optional[StanceDistribution] = Field(
        None,
        description="Stance distribution (available when stance model is ready)"
    )

    class Config:
        from_attributes = True


# ========================================
# Article Schemas
# ========================================

class ArticleSummary(BaseModel):
    """Brief article information for list views."""
    id: int = Field(description="Article ID")
    title: str = Field(description="Article title")
    press: PressInfo = Field(description="Press information")
    published_at: datetime = Field(description="Publication datetime (UTC)")
    image_url: Optional[str] = Field(None, description="Thumbnail image URL")
    stance: Optional[StanceType] = Field(None, description="Stance (when model is ready)")
    similarity_score: Optional[float] = Field(
        None,
        ge=0,
        le=1,
        description="Similarity score to topic (if queried by topic)"
    )

    class Config:
        from_attributes = True


class ArticleDetail(BaseModel):
    """Detailed article information."""
    id: int = Field(description="Article ID")
    title: str = Field(description="Article title")
    content: str = Field(description="Full article content")
    summary: Optional[str] = Field(None, description="AI-generated summary")
    image_url: Optional[str] = Field(None, description="Article image URL")
    original_url: str = Field(description="Original article URL")
    published_at: datetime = Field(description="Publication datetime (UTC)")
    author: Optional[str] = Field(None, description="Article author")
    press: PressInfo = Field(description="Press information")
    topic: Optional["TopicBrief"] = Field(None, description="Associated topic (if any)")
    stance: Optional[StanceData] = Field(
        None,
        description="Stance analysis (available when model is ready)"
    )
    related_articles: Optional[List["RelatedArticle"]] = Field(
        None,
        description="Related articles from the same topic"
    )

    class Config:
        from_attributes = True


class RelatedArticle(BaseModel):
    """Related article with similarity score."""
    id: int = Field(description="Article ID")
    title: str = Field(description="Article title")
    press: PressInfo = Field(description="Press information")
    stance: Optional[StanceType] = Field(None, description="Article stance")
    similarity: float = Field(ge=0, le=1, description="Similarity score to main article")

    class Config:
        from_attributes = True


# ========================================
# Topic Schemas
# ========================================

class TopicBrief(BaseModel):
    """Brief topic information for references."""
    id: int = Field(description="Topic ID")
    name: str = Field(description="Topic title")

    class Config:
        from_attributes = True


class MainArticleInfo(BaseModel):
    """Main article information for topic."""
    id: int = Field(description="Article ID")
    title: str = Field(description="Article title")
    image_url: Optional[str] = Field(None, description="Article image URL")
    stance: Optional[StanceType] = Field(None, description="Article stance")

    class Config:
        from_attributes = True


class TopicSummary(BaseModel):
    """Brief topic information for list views."""
    id: int = Field(description="Topic ID")
    name: str = Field(description="Topic title")
    description: Optional[str] = Field(None, description="Topic description")
    article_count: int = Field(ge=0, description="Number of articles in topic")
    topic_rank: int = Field(ge=1, le=10, description="Topic ranking (1-10)")
    cluster_score: float = Field(description="Cluster importance score")
    topic_date: datetime = Field(description="Topic date")
    main_article: Optional[MainArticleInfo] = Field(
        None,
        description="Main representative article"
    )
    stance_distribution: Optional[StanceDistribution] = Field(
        None,
        description="Stance distribution (when model is ready)"
    )

    class Config:
        from_attributes = True


class TopicDetail(BaseModel):
    """Detailed topic information."""
    id: int = Field(description="Topic ID")
    name: str = Field(description="Topic title")
    description: Optional[str] = Field(None, description="Topic description")
    article_count: int = Field(ge=0, description="Number of articles")
    topic_date: datetime = Field(description="Topic date")
    topic_rank: int = Field(ge=1, le=10, description="Topic ranking")
    cluster_score: float = Field(description="Cluster importance score")
    main_article: Optional[ArticleDetail] = Field(
        None,
        description="Main representative article"
    )
    stance_distribution: Optional[StanceDistribution] = Field(
        None,
        description="Stance distribution (when model is ready)"
    )
    keywords: List[str] = Field(default_factory=list, description="Topic keywords")

    class Config:
        from_attributes = True


# ========================================
# Recommendation Schemas
# ========================================

class RecommendedArticle(BaseModel):
    """Recommended article with metadata."""
    id: int = Field(description="Article ID")
    title: str = Field(description="Article title")
    press: PressInfo = Field(description="Press information")
    similarity: float = Field(ge=0, le=1, description="Similarity score")
    stance: Optional[StanceType] = Field(None, description="Article stance")

    class Config:
        from_attributes = True


class TopicRecommendations(BaseModel):
    """Recommended articles by stance for a topic."""
    topic_id: int = Field(description="Topic ID")
    recommendations: "StanceRecommendations" = Field(
        description="Recommended articles grouped by stance"
    )


class StanceRecommendations(BaseModel):
    """Recommendations grouped by stance (Top 3 each)."""
    support: List[RecommendedArticle] = Field(
        default_factory=list,
        description="Top 3 support articles"
    )
    neutral: List[RecommendedArticle] = Field(
        default_factory=list,
        description="Top 3 neutral articles"
    )
    oppose: List[RecommendedArticle] = Field(
        default_factory=list,
        description="Top 3 opposition articles"
    )


# ========================================
# Health Check
# ========================================

class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(description="Service status")
    timestamp: datetime = Field(description="Current server time")
    database: str = Field(description="Database connection status")
    redis: str = Field(description="Redis connection status")


# ========================================
# Daily Keywords (Word Cloud)
# ========================================

class KeywordItem(BaseModel):
    """Single keyword with weight for word cloud."""
    text: str = Field(description="Keyword text")
    weight: float = Field(ge=0, description="Keyword weight (aggregated score)")

    class Config:
        from_attributes = True


class DailyKeywordsResponse(BaseModel):
    """Daily keywords response for word cloud visualization."""
    date: str = Field(description="News date (YYYY-MM-DD)")
    total_topics: int = Field(ge=0, description="Number of topics analyzed")
    keywords: List[KeywordItem] = Field(description="Top keywords with weights")

    class Config:
        from_attributes = True


# ========================================
# Press Stance Distribution
# ========================================

class TopicStanceInfo(BaseModel):
    """Topic stance information for a press."""
    topic_id: int = Field(description="Topic ID")
    topic_name: str = Field(description="Topic name")
    dominant_stance: StanceType = Field(description="Most common stance for this topic")
    distribution: StanceDistribution = Field(description="Stance distribution counts")

    class Config:
        from_attributes = True


class PressStanceInfo(BaseModel):
    """Press stance distribution across topics."""
    press_id: str = Field(description="Press ID")
    press_name: str = Field(description="Press name")
    topic_stances: List[TopicStanceInfo] = Field(description="Stance distribution per topic")

    class Config:
        from_attributes = True


class PressStanceDistributionResponse(BaseModel):
    """Press stance distribution response."""
    date: str = Field(description="News date (YYYY-MM-DD)")
    total_topics: int = Field(ge=0, description="Number of topics analyzed")
    press_list: List[PressStanceInfo] = Field(description="Stance distribution by press")

    class Config:
        from_attributes = True
