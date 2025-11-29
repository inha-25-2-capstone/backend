"""
Quick comparison test for improved BERTopic clustering
Uses psycopg2 directly (no SQLAlchemy dependency)
"""
import psycopg2
import json
from datetime import date
import requests
import time


def fetch_data_from_db(news_date):
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
            LIMIT 333
        """, (news_date,))

        rows = cur.fetchall()

        embeddings = []
        texts = []
        article_ids = []

        for row in rows:
            article_id, title, summary, embedding = row

            # Parse embedding string to list
            if isinstance(embedding, str):
                embedding = json.loads(embedding)
            embeddings.append(embedding)

            # Combine title + summary
            text = f"{title}. {summary or ''}"
            texts.append(text)
            article_ids.append(article_id)

        cur.close()

        print(f"✓ Fetched {len(article_ids)} articles with embeddings for {news_date}\n")

        return {
            'embeddings': embeddings,
            'texts': texts,
            'article_ids': article_ids,
            'news_date': str(news_date)
        }

    finally:
        conn.close()


def test_clustering(endpoint, name, data):
    """Test clustering endpoint."""
    print("=" * 80)
    print(f"TEST: {name}")
    print("=" * 80)

    url = f"https://gaaahee-news-stance-detection.hf.space{endpoint}"

    payload = {
        "embeddings": data['embeddings'],
        "texts": data['texts'],
        "article_ids": data['article_ids'],
        "news_date": data['news_date'],
        "min_topic_size": 5,
        "nr_topics": "auto",
        "include_visualization": False
    }

    print(f"Calling: {endpoint}")
    print(f"Articles: {len(data['article_ids'])}")
    print("(This may take 30-60 seconds...)\n")

    start_time = time.time()

    try:
        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
        result = response.json()

        elapsed = time.time() - start_time

        if result.get('success'):
            print(f"✓ Clustering successful ({elapsed:.1f}s)")
            print(f"  Total topics: {result['total_topics']}")
            print(f"  Outliers: {result['outliers']}\n")

            print(f"TOP 10 TOPICS ({name}):")
            print("-" * 80)

            for topic in result['topics'][:10]:
                if topic.get('topic_rank'):
                    word_count = len(topic['topic_title'].split())
                    print(f"\nRank {topic['topic_rank']}: '{topic['topic_title']}'")
                    print(f"  Articles: {topic['article_count']}")
                    print(f"  Words: {word_count}")
                    if topic.get('keywords'):
                        keywords = ', '.join([kw['keyword'] for kw in topic['keywords'][:5]])
                        print(f"  Keywords: {keywords}")

            # Statistics
            ranked_topics = [t for t in result['topics'] if t.get('topic_rank')]
            word_counts = [len(t['topic_title'].split()) for t in ranked_topics]

            if word_counts:
                print("\n" + "-" * 80)
                print("WORD COUNT STATISTICS:")
                print(f"  Min: {min(word_counts)}")
                print(f"  Max: {max(word_counts)}")
                print(f"  Avg: {sum(word_counts)/len(word_counts):.1f}")
                print(f"  3-6 words: {sum(1 for w in word_counts if 3 <= w <= 6)}/{len(word_counts)}")

            return result

        else:
            print(f"✗ Clustering failed: {result.get('error')}")
            return None

    except requests.Timeout:
        print(f"✗ Request timed out after 120 seconds")
        return None
    except requests.RequestException as e:
        print(f"✗ Request failed: {e}")
        return None
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Main test function."""
    print("=" * 80)
    print("BERTOPIC CLUSTERING COMPARISON TEST")
    print("Original (Mecab) vs Improved (Noun-only, 3-6 words)")
    print("=" * 80)
    print()

    # Fetch data
    news_date = date(2025, 11, 27)
    data = fetch_data_from_db(news_date)

    # Test 1: Original (Mecab)
    original_result = test_clustering(
        "/cluster-topics-mecab",
        "ORIGINAL (Mecab)",
        data
    )

    print("\n" * 2)

    # Test 2: Improved (Noun-only)
    improved_result = test_clustering(
        "/cluster-topics-improved",
        "IMPROVED (Noun-only, 3-6 words)",
        data
    )

    # Comparison
    print("\n" * 2)
    print("=" * 80)
    print("SIDE-BY-SIDE COMPARISON")
    print("=" * 80)

    if original_result and improved_result:
        print(f"\n{'Rank':<6} {'Original (Mecab)':<30} {'Improved (Noun-only)':<30} {'Words'}")
        print("-" * 90)

        for i in range(10):
            orig_topic = None
            imp_topic = None

            for t in original_result['topics']:
                if t.get('topic_rank') == i + 1:
                    orig_topic = t
                    break

            for t in improved_result['topics']:
                if t.get('topic_rank') == i + 1:
                    imp_topic = t
                    break

            if orig_topic or imp_topic:
                orig_title = orig_topic['topic_title'] if orig_topic else "-"
                imp_title = imp_topic['topic_title'] if imp_topic else "-"
                imp_words = len(imp_topic['topic_title'].split()) if imp_topic else 0

                print(f"{i+1:<6} {orig_title:<30} {imp_title:<30} {imp_words}")

    print("\n" + "=" * 80)
    print("Test complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
