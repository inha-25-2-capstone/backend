"""
Local test for improved BERTopic clustering (no HF Spaces needed)

Tests noun-only tokenizer and 3-6 word title generation locally.
"""
import sys
from pathlib import Path

# Add project root to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(backend_dir.parent / 'news-stance-detection'))

import psycopg2
from datetime import date
import numpy as np


def fetch_embeddings_from_db(news_date: date):
    """Fetch articles with embeddings from PostgreSQL."""
    conn = psycopg2.connect(
        host='localhost',
        port=5432,
        database='politics_news_dev',
        user='postgres',
        password='postgres'
    )

    try:
        cur = conn.cursor()

        # Fetch articles with embeddings
        cur.execute("""
            SELECT article_id, title, summary, embedding
            FROM article
            WHERE news_date = %s
              AND embedding IS NOT NULL
            ORDER BY article_id
        """, (news_date,))

        rows = cur.fetchall()

        embeddings = []
        texts = []
        article_ids = []

        for row in rows:
            article_id, title, summary, embedding = row

            # Convert embedding (stored as string representation) to list
            if isinstance(embedding, str):
                # Parse string like "[0.1, 0.2, ...]" to list
                import json
                embedding = json.loads(embedding)
            embeddings.append(embedding)

            # Combine title + summary
            text = f"{title}. {summary or ''}"
            texts.append(text)
            article_ids.append(article_id)

        cur.close()

        print(f"✓ Fetched {len(article_ids)} articles with embeddings for {news_date}")

        return {
            'embeddings': embeddings,
            'texts': texts,
            'article_ids': article_ids,
            'news_date': str(news_date)
        }

    finally:
        conn.close()


def test_improved_clustering():
    """Test improved clustering locally."""
    print("=" * 80)
    print("LOCAL IMPROVED CLUSTERING TEST")
    print("Settings: noun-only, ngram=(1,2), min_df=2, max_df=0.90")
    print("Title length: 3-6 words")
    print("=" * 80)

    # Fetch data
    news_date = date(2025, 11, 27)
    data = fetch_embeddings_from_db(news_date)

    print(f"\nData: {len(data['article_ids'])} articles\n")

    # Import improved clustering function
    try:
        from src.services.bertopic_clustering_improved import run_improved_bertopic_clustering

        print("Running improved BERTopic clustering...")
        print("(This may take 30-60 seconds with Mecab tokenization)\n")

        result = run_improved_bertopic_clustering(
            embeddings=data['embeddings'],
            texts=data['texts'],
            article_ids=data['article_ids'],
            news_date=data['news_date'],
            min_topic_size=5,
            nr_topics="auto",
            include_visualization=False
        )

        if result['success']:
            print(f"✓ Clustering successful!")
            print(f"  Total topics: {result['total_topics']}")
            print(f"  Outliers: {result['outliers']}\n")

            print("=" * 80)
            print("TOP 10 TOPICS (IMPROVED VERSION)")
            print("=" * 80)

            for topic in result['topics'][:10]:
                if topic['topic_rank']:
                    word_count = len(topic['topic_title'].split())

                    print(f"\nRank {topic['topic_rank']}: '{topic['topic_title']}'")
                    print(f"  Articles: {topic['article_count']}")
                    print(f"  Words: {word_count}")
                    print(f"  Keywords: {', '.join([kw['keyword'] for kw in topic['keywords'][:5]])}")

            # Statistics
            title_word_counts = [
                len(t['topic_title'].split()) for t in result['topics'][:10]
                if t['topic_rank']
            ]

            print("\n" + "=" * 80)
            print("TITLE WORD COUNT STATISTICS")
            print("=" * 80)
            print(f"Min: {min(title_word_counts)}")
            print(f"Max: {max(title_word_counts)}")
            print(f"Avg: {sum(title_word_counts)/len(title_word_counts):.1f}")
            print(f"3-6 words: {sum(1 for l in title_word_counts if 3 <= l <= 6)}/{len(title_word_counts)}")

            print("\n" + "=" * 80)
            print("COMPARISON WITH CURRENT DB")
            print("=" * 80)
            print("\nCurrent DB (all 3 words):")
            print("  1. 국민 의원 체포")
            print("  2. 철강 산업 강화")
            print("  3. 의회 광주 교육")
            print("  4. 리호 발사 성공")
            print("  5. 증원 감사원 의대")
            print("\nImproved (3-6 words with noun-only):")
            for i, topic in enumerate(result['topics'][:5], 1):
                if topic['topic_rank']:
                    print(f"  {i}. {topic['topic_title']}")

        else:
            print(f"✗ Clustering failed: {result.get('error')}")
            return

    except ImportError as e:
        print(f"✗ Import error: {e}")
        print("\nMake sure Mecab is installed:")
        print("  pip install konlpy")
        print("  # Install mecab-ko system package")
        return
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return

    print("\n" + "=" * 80)
    print("Test complete!")
    print("=" * 80)


if __name__ == "__main__":
    test_improved_clustering()
