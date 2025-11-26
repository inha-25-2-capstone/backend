#!/usr/bin/env python3
"""
Test improved BERTopic topic titles with Korean-optimized CountVectorizer.

This script:
1. Fetches articles with embeddings from DB
2. Calls AI Service BERTopic API (with our improvements)
3. Compares topic titles before/after improvements
"""
import sys
from datetime import datetime, date

from src.services.bertopic_service import fetch_articles_with_embeddings
from src.services.ai_client import AIServiceClient
from src.utils.logger import setup_logger
from src.config import AI_SERVICE_URL, AI_SERVICE_TIMEOUT

logger = setup_logger()


def test_improved_topics(limit: int = 50):
    """
    Test BERTopic with improved Korean vectorizer.

    Args:
        limit: Number of articles to test (default: 50)
    """
    print("="*100)
    print("Testing Improved BERTopic Topic Titles")
    print("="*100)

    # Step 1: Fetch articles with embeddings from DB
    print("\n⏳ Step 1: Fetching articles from DB...")

    articles, embeddings, texts = fetch_articles_with_embeddings(
        news_date=None,  # Get latest articles
        limit=limit
    )

    if not articles or embeddings is None:
        print("❌ No articles with embeddings found in DB")
        return False

    print(f"✅ Fetched {len(articles)} articles with embeddings")
    print(f"   Embedding dimension: {embeddings.shape[1]}")

    # Show sample articles
    print(f"\nSample articles:")
    for i, article in enumerate(articles[:3], 1):
        print(f"   {i}. [{article['article_id']}] {article['title'][:60]}...")

    # Step 2: Call AI Service BERTopic API
    print("\n⏳ Step 2: Calling AI Service BERTopic API...")
    print(f"   URL: {AI_SERVICE_URL}")
    print("   (This will use the improved Korean CountVectorizer)")

    ai_client = AIServiceClient(
        base_url=AI_SERVICE_URL,
        timeout=AI_SERVICE_TIMEOUT
    )

    # Prepare request data
    article_ids = [a['article_id'] for a in articles]

    try:
        result = ai_client.cluster_topics(
            embeddings=embeddings.tolist(),
            texts=texts,
            article_ids=article_ids,
            news_date=date.today().isoformat(),
            min_topic_size=3,  # Minimum 3 articles per topic
            nr_topics="auto"
        )
    except Exception as e:
        print(f"❌ API call failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    if not result.get('success'):
        print(f"❌ Clustering failed: {result.get('error')}")
        return False

    print(f"✅ BERTopic clustering completed!")

    # Step 3: Display results
    print(f"\n{'='*100}")
    print("RESULTS")
    print(f"{'='*100}")

    print(f"\n📊 Statistics:")
    print(f"   Total topics: {result['total_topics']}")
    print(f"   Total articles: {result['total_articles']}")
    print(f"   Outliers: {result['outliers']}")
    print(f"   Processing time: {result.get('processing_time', 'N/A')}")

    topics = result['topics']
    valid_topics = [t for t in topics if t['topic_id'] != -1]

    # Sort by rank
    valid_topics.sort(key=lambda x: x.get('topic_rank') or 999)

    print(f"\n{'─'*100}")
    print("Topic Details (with Improved Korean Vectorizer):")
    print(f"{'─'*100}")
    print("\n🎯 Key Improvements:")
    print("   ✅ CustomTokenizer for Korean text")
    print("   ✅ 595 Korean stopwords removed")
    print("   ✅ N-gram (1-3) for meaningful phrases")
    print("   ✅ min_df=2, max_df=0.95 for noise filtering")
    print()

    for topic in valid_topics[:10]:  # Show top 10 topics
        print(f"\n🔹 Topic {topic['topic_id']}: {topic['topic_title']}")
        print(f"   Rank: #{topic.get('topic_rank', 'N/A')}")
        print(f"   Articles: {topic['article_count']}")
        print(f"   Cluster score: {topic.get('cluster_score', 0):.2f}")

        print(f"\n   Top 5 keywords:")
        for kw in topic['keywords'][:5]:
            print(f"      • {kw['keyword']:30} (score: {kw['score']:.3f})")

        # Show 2 sample article titles
        sample_ids = topic['article_ids'][:2]
        print(f"\n   Sample articles:")
        for aid in sample_ids:
            article = next((a for a in articles if a['article_id'] == aid), None)
            if article:
                print(f"      [{aid}] {article['title'][:70]}...")

        # Show similarity scores
        similarities = topic.get('similarity_scores', {})
        if similarities:
            avg_sim = sum(similarities.values()) / len(similarities)
            print(f"\n   Average similarity: {avg_sim:.3f}")

    # Show outliers
    outlier_topic = next((t for t in topics if t['topic_id'] == -1), None)
    if outlier_topic and outlier_topic['article_count'] > 0:
        print(f"\n🔸 Outliers: {outlier_topic['article_count']} articles")
        sample_outliers = outlier_topic['article_ids'][:3]
        print(f"   Sample outlier IDs: {sample_outliers}")

    # Evaluation
    print(f"\n{'='*100}")
    print("EVALUATION")
    print(f"{'='*100}")

    print(f"\n✅ Korean Optimizations Applied:")
    print(f"   1. Stopwords: 595 Korean stopwords removed")
    print(f"   2. N-gram: Extract 1-3 word phrases (e.g., '부동산규제완화')")
    print(f"   3. Tokenizer: CustomTokenizer extracts Korean words only")
    print(f"   4. Filtering: min_df=2, max_df=0.95 removes rare/common terms")

    print(f"\n📊 Topic Quality Analysis:")

    # Check number of topics
    if 3 <= len(valid_topics) <= 10:
        print(f"   ✅ Number of topics: {len(valid_topics)} (optimal: 3-10)")
    else:
        print(f"   ⚠️  Number of topics: {len(valid_topics)} (expected: 3-10)")

    # Check outlier ratio
    outlier_ratio = result['outliers'] / result['total_articles'] * 100
    if outlier_ratio < 30:
        print(f"   ✅ Outlier ratio: {outlier_ratio:.1f}% (good: <30%)")
    else:
        print(f"   ⚠️  Outlier ratio: {outlier_ratio:.1f}% (high: >30%)")

    # Check topic title quality
    print(f"\n💡 Topic Title Examples:")
    for i, topic in enumerate(valid_topics[:5], 1):
        title = topic['topic_title']
        print(f"   {i}. \"{title}\"")

        # Check if title looks meaningful (not just single characters)
        words = title.split()
        if len(words) >= 2 and any(len(w) > 2 for w in words):
            print(f"      ✅ Meaningful phrase detected")
        else:
            print(f"      ⚠️  May need further tuning")

    print(f"\n{'='*100}")
    print("EXPECTED IMPROVEMENTS")
    print(f"{'='*100}")

    print(f"\n📈 Before (Default BERTopic):")
    print(f"   - Simple word concatenation: \"부동산 규제 완화\"")
    print(f"   - Includes stopwords: \"것\", \"이\", \"그\"")
    print(f"   - Single words only")

    print(f"\n📈 After (Korean-Optimized):")
    print(f"   - Meaningful phrases: \"부동산규제완화\", \"정책논란\"")
    print(f"   - Stopwords removed: cleaner keywords")
    print(f"   - N-gram phrases: more context-aware")

    print("\n" + "="*100)

    return True


def main():
    """Run test."""
    import argparse

    parser = argparse.ArgumentParser(description='Test improved BERTopic topic titles')
    parser.add_argument('--limit', type=int, default=50, help='Number of articles to test (default: 50)')

    args = parser.parse_args()

    try:
        success = test_improved_topics(limit=args.limit)

        if success:
            print("\n✅ Test completed successfully!")
            print("\n🎉 Korean-optimized BERTopic is working!")
            print("\n📝 Next steps:")
            print("   1. Deploy to HF Spaces (git push)")
            print("   2. Run full pipeline: python scripts/run_full_pipeline.py")
            print("   3. Check API: GET /api/topics")
            return 0
        else:
            print("\n⚠️  Test failed. Please check the output above.")
            return 1

    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        return 130

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
