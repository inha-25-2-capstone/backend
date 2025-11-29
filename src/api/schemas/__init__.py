"""
API schemas package.
"""
from .common import (
    StanceType,
    PaginationParams,
    PaginationMeta,
    PaginatedResponse,
    StanceData,
    StanceProbabilities,
    StanceDistribution,
)
from .responses import (
    # Press
    PressInfo,
    PressDetail,
    # Article
    ArticleSummary,
    ArticleDetail,
    RelatedArticle,
    # Topic
    TopicBrief,
    TopicSummary,
    TopicDetail,
    MainArticleInfo,
    # Recommendations
    RecommendedArticle,
    TopicRecommendations,
    StanceRecommendations,
    # Health
    HealthResponse,
    # Daily Keywords
    DailyKeywordsResponse,
    KeywordItem,
)

__all__ = [
    # Common
    "StanceType",
    "PaginationParams",
    "PaginationMeta",
    "PaginatedResponse",
    "StanceData",
    "StanceProbabilities",
    "StanceDistribution",
    # Press
    "PressInfo",
    "PressDetail",
    # Article
    "ArticleSummary",
    "ArticleDetail",
    "RelatedArticle",
    # Topic
    "TopicBrief",
    "TopicSummary",
    "TopicDetail",
    "MainArticleInfo",
    # Recommendations
    "RecommendedArticle",
    "TopicRecommendations",
    "StanceRecommendations",
    # Health
    "HealthResponse",
    # Daily Keywords
    "DailyKeywordsResponse",
    "KeywordItem",
]
