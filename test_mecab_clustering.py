#!/usr/bin/env python3
"""
Test Mecab-based BERTopic clustering with real DB data.

This script:
1. Fetches articles with embeddings from DB
2. Calls BOTH CustomTokenizer AND Mecab clustering APIs
3. Compares topic quality between two approaches
"""
import sys
from datetime import date

from src.services.bertopic_service import fetch_articles_with_embeddings
from src.services.ai_client import AIServiceClient
from src.utils.logger import setup_logger
from src.config import AI_SERVICE_URL, AI_SERVICE_TIMEOUT

logger = setup_logger()


def test_mecab_clustering(limit: int = 50):
    """
    Test Mecab-based BERTopic and compare with CustomTokenizer.

    Args:
        limit: Number of articles to test (default: 50)
    """
    print("="*100)
    print("Testing Mecab-based BERTopic vs CustomTokenizer")
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

    ai_client = AIServiceClient(
        base_url=AI_SERVICE_URL,
        timeout=AI_SERVICE_TIMEOUT
    )

    article_ids = [a['article_id'] for a in articles]
    today = date.today().isoformat()

    # =================================================================
    # Test 1: Mecab-based clustering
    # =================================================================
    print(f"\n{'='*100}")
    print("TEST 1: Mecab-based BERTopic (KoBERTopic approach)")
    print(f"{'='*100}")
    print(f"   URL: {AI_SERVICE_URL}/cluster-topics-mecab")
    print("   Features:")
    print("   • Mecab morphological analyzer")
    print("   • max_features=3000 (top 3000 features only)")
    print("   • Default min_df, max_df (no custom filtering)")
    print("   • ngram_range=(1,3)")
    print()

    try:
        mecab_result = ai_client.cluster_topics_mecab(
            embeddings=embeddings.tolist(),
            texts=texts,
            article_ids=article_ids,
            news_date=today,
            min_topic_size=3,
            nr_topics="auto"
        )
    except AttributeError:
        # Add method to ai_client if it doesn't exist
        import requests
        print("⏳ Calling Mecab API directly...")
        response = requests.post(
            f"{AI_SERVICE_URL}/cluster-topics-mecab",
            json={
                "embeddings": embeddings.tolist(),
                "texts": texts,
                "article_ids": article_ids,
                "news_date": today,
                "min_topic_size": 3,
                "nr_topics": "auto"
            },
            timeout=AI_SERVICE_TIMEOUT
        )
        if response.status_code != 200:
            print(f"❌ Mecab clustering failed: {response.status_code}")
            print(f"   Error: {response.text}")
            return False
        mecab_result = response.json()
    except Exception as e:
        print(f"❌ Mecab clustering failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    if not mecab_result.get('success'):
        print(f"❌ Mecab clustering failed: {mecab_result.get('error')}")
        return False

    print(f"✅ Mecab clustering completed!")
    print(f"\n📊 Mecab Statistics:")
    print(f"   Total topics: {mecab_result['total_topics']}")
    print(f"   Total articles: {mecab_result['total_articles']}")
    print(f"   Outliers: {mecab_result['outliers']}")

    mecab_topics = [t for t in mecab_result['topics'] if t['topic_id'] != -1]
    mecab_topics.sort(key=lambda x: x.get('topic_rank') or 999)

    print(f"\n🎯 Mecab Topics:")
    for topic in mecab_topics[:10]:
        print(f"\n   Topic {topic['topic_id']}: {topic['topic_title']}")
        print(f"   Rank: #{topic.get('topic_rank', 'N/A')}")
        print(f"   Articles: {topic['article_count']}")
        print(f"   Top 5 keywords: {', '.join([kw['keyword'] for kw in topic['keywords'][:5]])}")

    # =================================================================
    # Test 2: CustomTokenizer clustering (for comparison)
    # =================================================================
    print(f"\n{'='*100}")
    print("TEST 2: CustomTokenizer-based BERTopic (Original)")
    print(f"{'='*100}")
    print(f"   URL: {AI_SERVICE_URL}/cluster-topics")
    print("   Features:")
    print("   • CustomTokenizer (regex-based)")
    print("   • 595 Korean stopwords")
    print("   • min_df=2, max_df=0.6")
    print("   • ngram_range=(1,3)")
    print()

    try:
        custom_result = ai_client.cluster_topics(
            embeddings=embeddings.tolist(),
            texts=texts,
            article_ids=article_ids,
            news_date=today,
            min_topic_size=3,
            nr_topics="auto"
        )
    except Exception as e:
        print(f"❌ CustomTokenizer clustering failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    if not custom_result.get('success'):
        print(f"❌ CustomTokenizer clustering failed: {custom_result.get('error')}")
        return False

    print(f"✅ CustomTokenizer clustering completed!")
    print(f"\n📊 CustomTokenizer Statistics:")
    print(f"   Total topics: {custom_result['total_topics']}")
    print(f"   Total articles: {custom_result['total_articles']}")
    print(f"   Outliers: {custom_result['outliers']}")

    custom_topics = [t for t in custom_result['topics'] if t['topic_id'] != -1]
    custom_topics.sort(key=lambda x: x.get('topic_rank') or 999)

    print(f"\n🎯 CustomTokenizer Topics:")
    for topic in custom_topics[:10]:
        print(f"\n   Topic {topic['topic_id']}: {topic['topic_title']}")
        print(f"   Rank: #{topic.get('topic_rank', 'N/A')}")
        print(f"   Articles: {topic['article_count']}")
        print(f"   Top 5 keywords: {', '.join([kw['keyword'] for kw in topic['keywords'][:5]])}")

    # =================================================================
    # Comparison Analysis
    # =================================================================
    print(f"\n{'='*100}")
    print("COMPARISON ANALYSIS")
    print(f"{'='*100}")

    print(f"\n📊 Topic Count:")
    print(f"   Mecab:           {mecab_result['total_topics']} topics")
    print(f"   CustomTokenizer: {custom_result['total_topics']} topics")

    print(f"\n📊 Outlier Ratio:")
    mecab_outlier_ratio = mecab_result['outliers'] / mecab_result['total_articles'] * 100
    custom_outlier_ratio = custom_result['outliers'] / custom_result['total_articles'] * 100
    print(f"   Mecab:           {mecab_outlier_ratio:.1f}%")
    print(f"   CustomTokenizer: {custom_outlier_ratio:.1f}%")

    print(f"\n💡 Topic Title Quality Comparison:")
    print(f"\n   Mecab Topics:")
    for i, topic in enumerate(mecab_topics[:5], 1):
        title = topic['topic_title']
        print(f"      {i}. \"{title}\"")

    print(f"\n   CustomTokenizer Topics:")
    for i, topic in enumerate(custom_topics[:5], 1):
        title = topic['topic_title']
        print(f"      {i}. \"{title}\"")

    # Check for generic words in Mecab results
    print(f"\n🔍 Checking for generic Korean words in Mecab topics...")
    generic_words = ['있는', '것을', '대한', '이다', '그', '것']
    mecab_has_generic = False
    for topic in mecab_topics[:10]:
        keywords = [kw['keyword'] for kw in topic['keywords'][:10]]
        for word in generic_words:
            if word in keywords:
                print(f"   ⚠️  Topic {topic['topic_id']}: Found '{word}' in keywords")
                mecab_has_generic = True

    if not mecab_has_generic:
        print(f"   ✅ No generic words found in Mecab topics (GOOD!)")

    print(f"\n{'='*100}")
    print("✅ Test completed!")
    print(f"{'='*100}")

    print(f"\n📝 Expected Improvements with Mecab:")
    print(f"   ✅ Cleaner topic titles (no generic words like '있는', '것을')")
    print(f"   ✅ Better morphological analysis (형태소 단위)")
    print(f"   ✅ max_features=3000 limits to most important features")
    print(f"   ✅ Default filtering (no aggressive max_df that causes issues)")

    return True


def main():
    """Run test."""
    import argparse

    parser = argparse.ArgumentParser(description='Test Mecab-based BERTopic clustering')
    parser.add_argument('--limit', type=int, default=50, help='Number of articles to test (default: 50)')

    args = parser.parse_args()

    try:
        success = test_mecab_clustering(limit=args.limit)

        if success:
            print("\n✅ Mecab clustering test completed successfully!")
            print("\n🎉 Next steps:")
            print("   1. Compare topic quality between Mecab and CustomTokenizer")
            print("   2. If Mecab is better, switch to /cluster-topics-mecab in pipeline")
            print("   3. Update backend to use Mecab endpoint")
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
