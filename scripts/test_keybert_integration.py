#!/usr/bin/env python3
"""
Test KeyBERT topic generation integration with HF Spaces.

This script tests the /generate-topics endpoint on the deployed AI service
and verifies it works correctly with Korean political news articles.
"""

import sys
from pathlib import Path
import requests
import json
from datetime import datetime

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import AI_SERVICE_URL, AI_SERVICE_TIMEOUT
from src.utils.logger import setup_logger

logger = setup_logger("test_keybert", level="INFO")


def test_health_check():
    """Test /health endpoint to verify service is running."""
    url = f"{AI_SERVICE_URL}/health"
    logger.info(f"Testing health check: {url}")

    try:
        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            result = response.json()
            logger.info("✅ Service is healthy")
            logger.info(f"   Summarization model: {result.get('summarization_model')}")
            logger.info(f"   Embedding model: {result.get('embedding_model')}")
            logger.info(f"   Device: {result.get('device')}")
            return True
        else:
            logger.error(f"❌ Health check failed: {response.status_code}")
            logger.error(f"   Response: {response.text}")
            return False

    except Exception as e:
        logger.error(f"❌ Health check error: {e}")
        return False


def test_generate_topics():
    """Test /generate-topics endpoint with sample Korean news."""
    url = f"{AI_SERVICE_URL}/generate-topics"
    logger.info(f"\nTesting topic generation: {url}")

    # Sample clusters with Korean political news
    test_clusters = [
        {
            "cluster_id": 1,
            "representative_articles": [
                {
                    "title": "정부, 부동산 규제 완화 발표",
                    "summary": "정부가 주택담보대출 규제를 완화하며 부동산 시장 활성화를 도모한다. 금융당국은 대출 한도를 상향 조정하고 규제지역을 축소하기로 했다."
                },
                {
                    "title": "야당, 부동산 정책 비판",
                    "summary": "야당은 정부의 부동산 규제 완화 방안이 서민들의 주거 불안을 가중시킬 것이라고 비판했다. 집값 상승 우려가 커지고 있다."
                },
                {
                    "title": "전문가들, 부동산 시장 전망 엇갈려",
                    "summary": "부동산 전문가들은 정부의 규제 완화 정책에 대한 시장 반응이 엇갈릴 것으로 전망했다. 일부는 시장 안정화를, 일부는 가격 급등을 예측했다."
                }
            ]
        },
        {
            "cluster_id": 2,
            "representative_articles": [
                {
                    "title": "국정감사, 정부 정책 점검",
                    "summary": "국회에서 정부 부처에 대한 국정감사가 시작됐다. 여야 의원들이 정부 정책의 문제점을 지적하고 개선을 촉구했다."
                },
                {
                    "title": "국정감사장 '설전'... 여야 공방 격화",
                    "summary": "국정감사장에서 여야 의원들의 설전이 이어졌다. 정부 정책을 둘러싼 공방이 격화되며 의견 대립이 심화됐다."
                }
            ]
        },
        {
            "cluster_id": 3,
            "representative_articles": [
                {
                    "title": "한미 국방장관, 북한 위협 대응 논의",
                    "summary": "한미 양국 국방장관이 회담을 갖고 북한의 군사 위협에 대한 공동 대응 방안을 논의했다. 양국은 연합방위태세를 강화하기로 합의했다."
                },
                {
                    "title": "북한 미사일 도발, 안보리 규탄",
                    "summary": "북한의 미사일 발사에 대해 유엔 안전보장이사회가 긴급회의를 열고 규탄 성명을 발표했다."
                }
            ]
        }
    ]

    payload = {
        "clusters": test_clusters,
        "top_n_keywords": 3,
        "keyphrase_ngram_range": [2, 4]
    }

    try:
        logger.info(f"Sending request with {len(test_clusters)} clusters...")
        response = requests.post(
            url,
            json=payload,
            timeout=AI_SERVICE_TIMEOUT
        )

        if response.status_code == 200:
            result = response.json()
            logger.info("✅ Topic generation SUCCESS")
            logger.info(f"   Clusters processed: {result['total_clusters']}")
            logger.info(f"   Processing time: {result['processing_time_seconds']}s")
            logger.info("\n" + "=" * 80)
            logger.info("GENERATED TOPICS")
            logger.info("=" * 80)

            for topic in result['topics']:
                logger.info(f"\n📌 Cluster {topic['cluster_id']}: {topic['topic_title']}")
                logger.info("   Keywords:")
                for kw in topic['keywords']:
                    logger.info(f"     - {kw['keyword']} (score: {kw['score']:.3f})")

            logger.info("\n" + "=" * 80)
            return True

        else:
            logger.error(f"❌ Topic generation failed: {response.status_code}")
            logger.error(f"   Response: {response.text}")
            return False

    except Exception as e:
        logger.error(f"❌ Topic generation error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_with_db_data():
    """Test topic generation with actual data from database."""
    logger.info("\n" + "=" * 80)
    logger.info("TESTING WITH DATABASE DATA")
    logger.info("=" * 80)

    try:
        from src.models.database import get_db_cursor
        from datetime import datetime, timedelta

        # Get yesterday's date (default news date)
        news_date = datetime.now() - timedelta(days=1)
        news_date = news_date.replace(hour=0, minute=0, second=0, microsecond=0)

        logger.info(f"Fetching articles from DB for date: {news_date.date()}")

        with get_db_cursor() as cur:
            # Get articles with embeddings
            cur.execute(
                """
                SELECT article_id, title, summary
                FROM article
                WHERE news_date = %s
                  AND summary IS NOT NULL
                  AND embedding IS NOT NULL
                ORDER BY article_id
                LIMIT 20
                """,
                (news_date,)
            )
            articles = cur.fetchall()

        if not articles:
            logger.warning("⚠️  No articles found in database for testing")
            return False

        logger.info(f"Found {len(articles)} articles")

        # Create a single test cluster from these articles
        # Take first 5 as representative articles
        representative = [
            {
                "title": article['title'],
                "summary": article['summary'] or article['title']  # Fallback to title
            }
            for article in articles[:5]
        ]

        test_cluster = [{
            "cluster_id": 999,
            "representative_articles": representative
        }]

        logger.info(f"Testing with {len(representative)} representative articles...")

        payload = {
            "clusters": test_cluster,
            "top_n_keywords": 3,
            "keyphrase_ngram_range": [2, 4]
        }

        url = f"{AI_SERVICE_URL}/generate-topics"
        response = requests.post(url, json=payload, timeout=AI_SERVICE_TIMEOUT)

        if response.status_code == 200:
            result = response.json()
            topic = result['topics'][0]

            logger.info("✅ DB data test SUCCESS")
            logger.info(f"\n📌 Generated topic title: {topic['topic_title']}")
            logger.info("   Keywords:")
            for kw in topic['keywords']:
                logger.info(f"     - {kw['keyword']} (score: {kw['score']:.3f})")

            logger.info("\n   Source articles:")
            for i, article in enumerate(representative, 1):
                logger.info(f"     {i}. {article['title'][:60]}...")

            return True
        else:
            logger.error(f"❌ DB test failed: {response.status_code}")
            logger.error(f"   Response: {response.text}")
            return False

    except Exception as e:
        logger.error(f"❌ DB test error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    logger.info("\n" + "=" * 80)
    logger.info("KEYBERT INTEGRATION TEST")
    logger.info("=" * 80)
    logger.info(f"AI Service URL: {AI_SERVICE_URL}")
    logger.info(f"Timeout: {AI_SERVICE_TIMEOUT}s")
    logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 80)

    results = {
        "health": False,
        "basic_test": False,
        "db_test": False
    }

    # Test 1: Health check
    logger.info("\n[1/3] Health Check")
    results["health"] = test_health_check()

    if not results["health"]:
        logger.error("\n❌ Service is not healthy. Skipping other tests.")
        return 1

    # Test 2: Basic topic generation
    logger.info("\n[2/3] Basic Topic Generation")
    results["basic_test"] = test_generate_topics()

    # Test 3: With database data
    logger.info("\n[3/3] Database Integration")
    results["db_test"] = test_with_db_data()

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Health Check: {'✅ PASS' if results['health'] else '❌ FAIL'}")
    logger.info(f"Basic Test: {'✅ PASS' if results['basic_test'] else '❌ FAIL'}")
    logger.info(f"DB Test: {'✅ PASS' if results['db_test'] else '❌ FAIL'}")
    logger.info("=" * 80)

    all_passed = all(results.values())
    if all_passed:
        logger.info("\n🎉 All tests PASSED!")
        return 0
    else:
        logger.error("\n❌ Some tests FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
