"""
BERTopic Clustering Service (Backend)

Runs BERTopic clustering using embeddings stored in database.
Uses sklearn's BERTopic with CustomTokenizer for Korean text.
"""
import numpy as np
from typing import List, Dict, Any, Optional
from datetime import datetime
from bertopic import BERTopic
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.models.database import get_db_connection
from src.utils.logger import setup_logger

logger = setup_logger()


def calculate_cosine_similarity(embedding1: np.ndarray, embedding2: np.ndarray) -> float:
    """
    Calculate cosine similarity between two embeddings.

    Args:
        embedding1: First embedding vector
        embedding2: Second embedding vector

    Returns:
        Cosine similarity score (0 to 1)
    """
    # Reshape to 2D for sklearn
    emb1 = embedding1.reshape(1, -1)
    emb2 = embedding2.reshape(1, -1)

    similarity = cosine_similarity(emb1, emb2)[0][0]

    # Ensure range [0, 1]
    return float(max(0.0, min(1.0, similarity)))


class CustomTokenizer:
    """
    Simple Korean tokenizer for BERTopic (regex-based).
    Same as HF Spaces version for consistency.
    """

    def __init__(self):
        pass

    def __call__(self, sent):
        """
        Tokenize Korean sentence.
        Extract Korean words, filter by length > 1.
        """
        import re
        try:
            if not sent:
                return []

            sent = sent[:1000000]  # Limit length
            word_tokens = re.findall(r'[가-힣]+', sent)
            result = [word for word in word_tokens if len(word) > 1]
            return result

        except:
            return []


def fetch_articles_with_embeddings(news_date: Optional[datetime.date] = None, limit: int = 200):
    """
    Fetch articles with embeddings from database.

    Args:
        news_date: Optional date to filter by news_date
        limit: Maximum number of articles

    Returns:
        Tuple of (articles, embeddings, doc_texts):
        - articles: List of dicts with article_id, title, summary
        - embeddings: numpy array of shape (n_articles, 768)
        - doc_texts: List of "title. summary" strings
    """
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            if news_date:
                query = """
                    SELECT article_id, title, summary, embedding
                    FROM article
                    WHERE summary IS NOT NULL
                      AND embedding IS NOT NULL
                      AND news_date = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """
                cursor.execute(query, (news_date, limit))
            else:
                query = """
                    SELECT article_id, title, summary, embedding
                    FROM article
                    WHERE summary IS NOT NULL
                      AND embedding IS NOT NULL
                    ORDER BY created_at DESC
                    LIMIT %s
                """
                cursor.execute(query, (limit,))

            rows = cursor.fetchall()

            if not rows:
                logger.warning("No articles with embeddings found")
                return [], None, []

            articles = []
            embeddings_list = []
            doc_texts = []

            for row in rows:
                articles.append({
                    'article_id': row[0],
                    'title': row[1],
                    'summary': row[2]
                })

                # Embedding from pgvector - convert from string if needed
                embedding = row[3]
                if isinstance(embedding, str):
                    # Parse string representation: "[0.1, 0.2, ...]"
                    import json
                    embedding = json.loads(embedding)
                embeddings_list.append(embedding)

                # Document text for BERTopic (title + summary)
                doc_texts.append(f"{row[1]}. {row[2]}")

            # Convert to numpy array
            embeddings_array = np.array(embeddings_list, dtype=np.float32)

            logger.info(f"Fetched {len(articles)} articles with embeddings")

            return articles, embeddings_array, doc_texts


def run_bertopic_clustering(
    news_date: Optional[datetime.date] = None,
    limit: int = 200,
    min_topic_size: int = 5,
    nr_topics: str = "auto"
) -> Dict[str, Any]:
    """
    Run BERTopic clustering on articles from database.

    Args:
        news_date: Optional date to filter articles
        limit: Maximum number of articles
        min_topic_size: Minimum articles per topic
        nr_topics: Number of topics ("auto" or integer)

    Returns:
        Dict with clustering results:
        {
            'success': bool,
            'topics': List[dict],  # topic_id, title, keywords, article_ids, count, centroid, similarity_scores
            'total_topics': int,
            'total_articles': int,
            'outliers': int,
            'articles': List[dict],  # Original articles
            'news_date': date
        }
    """
    logger.info(f"Starting BERTopic clustering (news_date={news_date}, limit={limit})")

    try:
        # Fetch articles with embeddings
        articles, embeddings, doc_texts = fetch_articles_with_embeddings(news_date, limit)

        if not articles or embeddings is None:
            return {
                'success': False,
                'error': 'No articles with embeddings found',
                'total_articles': 0
            }

        if len(articles) < min_topic_size:
            return {
                'success': False,
                'error': f'Not enough articles for clustering ({len(articles)} < {min_topic_size})',
                'total_articles': len(articles)
            }

        logger.info(f"Clustering {len(articles)} articles with pre-computed embeddings")

        # Use BERTopic's default vectorizer which works better with its internal processing
        # The default CountVectorizer handles Korean text reasonably well via character n-grams
        topic_model = BERTopic(
            language="multilingual",  # Better for non-English languages
            nr_topics=nr_topics,
            min_topic_size=min_topic_size,
            top_n_words=10,
            calculate_probabilities=False,
            verbose=False
        )

        # Fit and transform with pre-computed embeddings
        topic_assignments, probs = topic_model.fit_transform(doc_texts, embeddings=embeddings)

        logger.info(f"Clustering complete. Found {len(set(topic_assignments))} topics")

        # Extract topic information
        topic_info = topic_model.get_topic_info()

        topics = []
        outliers = 0

        for idx, row in topic_info.iterrows():
            topic_id = int(row['Topic'])
            count = int(row['Count'])

            # Get topic words from c-TF-IDF
            topic_words = topic_model.get_topic(topic_id)

            # Get article indices and IDs for this topic
            article_indices = [i for i, t in enumerate(topic_assignments) if t == topic_id]
            article_ids = [articles[i]['article_id'] for i in article_indices]

            # Calculate topic centroid (mean of all embeddings in this topic)
            if article_indices:
                topic_embeddings = embeddings[article_indices]
                centroid = np.mean(topic_embeddings, axis=0)

                # Calculate similarity scores for each article in this topic
                similarity_scores = {}
                for i in article_indices:
                    article_id = articles[i]['article_id']
                    article_embedding = embeddings[i]
                    similarity = calculate_cosine_similarity(article_embedding, centroid)
                    similarity_scores[article_id] = similarity
            else:
                centroid = None
                similarity_scores = {}

            if topic_id == -1:
                # Outliers
                outliers = count
                topics.append({
                    'topic_id': topic_id,
                    'topic_title': '기타 (Outliers)',
                    'keywords': [],
                    'article_ids': article_ids,
                    'article_count': count,
                    'centroid': centroid.tolist() if centroid is not None else None,
                    'similarity_scores': similarity_scores
                })
            else:
                # Regular topic
                if topic_words:
                    # Top 3 words for title
                    top_words = [word for word, score in topic_words[:3]]
                    topic_title = ' '.join(top_words)

                    # Top 10 keywords with scores
                    keywords = [
                        {'keyword': word, 'score': float(score)}
                        for word, score in topic_words[:10]
                    ]
                else:
                    topic_title = f"Topic {topic_id}"
                    keywords = []

                topics.append({
                    'topic_id': topic_id,
                    'topic_title': topic_title,
                    'keywords': keywords,
                    'article_ids': article_ids,
                    'article_count': count,
                    'centroid': centroid.tolist() if centroid is not None else None,
                    'similarity_scores': similarity_scores
                })

        total_topics = len([t for t in topics if t['topic_id'] != -1])

        # Determine news_date
        if news_date:
            result_date = news_date
        else:
            # Use most common news_date from articles
            news_dates = []
            for article in articles:
                article_data = get_article_news_date(article['article_id'])
                if article_data:
                    news_dates.append(article_data)

            result_date = max(set(news_dates), key=news_dates.count) if news_dates else datetime.now().date()

        logger.info(f"Clustering successful: {total_topics} topics, {outliers} outliers")

        return {
            'success': True,
            'topics': topics,
            'total_topics': total_topics,
            'total_articles': len(articles),
            'outliers': outliers,
            'articles': articles,
            'news_date': result_date
        }

    except Exception as e:
        logger.error(f"BERTopic clustering failed: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
            'total_articles': 0
        }


def get_article_news_date(article_id: int) -> Optional[datetime.date]:
    """Get news_date for an article."""
    from src.models.database import ArticleRepository
    article = ArticleRepository.get_by_id(article_id)
    return article['news_date'] if article else None
