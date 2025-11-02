#!/usr/bin/env python3
"""
Compare KeyBERT vs TF-IDF topic generation methods.

This script tests both methods side-by-side to determine which produces
better quality topic titles for Korean political news.
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

logger = setup_logger("compare_topics", level="INFO")


# Test clusters with Korean political news
TEST_CLUSTERS = [
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
            },
            {
                "title": "야당, 국정감사서 정부 예산 낭비 지적",
                "summary": "야당은 국정감사에서 정부의 예산 낭비와 비효율적인 사업 집행을 집중적으로 공격했다."
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
            },
            {
                "title": "북한, 연이은 도발... 한반도 긴장 고조",
                "summary": "북한이 연이어 도발을 계속하면서 한반도의 군사적 긴장이 고조되고 있다. 전문가들은 추가 도발 가능성을 경고했다."
            }
        ]
    }
]


def test_method(method: str, use_phrases: bool = True):
    """
    Test topic generation with specified method.

    Args:
        method: 'tfidf' or 'keybert'
        use_phrases: Whether to use multi-word phrases (TF-IDF only)

    Returns:
        Tuple of (success, results, processing_time)
    """
    url = f"{AI_SERVICE_URL}/generate-topics"

    payload = {
        "clusters": TEST_CLUSTERS,
        "top_n_keywords": 3,
        "method": method,
        "use_phrases": use_phrases,
        "keyphrase_ngram_range": [2, 4]
    }

    try:
        logger.info(f"Testing {method.upper()} method...")
        response = requests.post(url, json=payload, timeout=AI_SERVICE_TIMEOUT)

        if response.status_code == 200:
            result = response.json()
            return True, result['topics'], result['processing_time_seconds']
        else:
            logger.error(f"{method.upper()} failed: {response.status_code}")
            logger.error(f"Response: {response.text}")
            return False, None, 0

    except Exception as e:
        logger.error(f"{method.upper()} error: {e}")
        return False, None, 0


def print_comparison(tfidf_results, keybert_results, tfidf_time, keybert_time):
    """Print side-by-side comparison of results."""

    logger.info("\n" + "=" * 100)
    logger.info("TOPIC GENERATION COMPARISON")
    logger.info("=" * 100)

    logger.info(f"\n{'TF-IDF (Statistical)':^50} | {'KeyBERT (Semantic)':^50}")
    logger.info(f"{'Processing Time: ' + str(tfidf_time) + 's':^50} | {'Processing Time: ' + str(keybert_time) + 's':^50}")
    logger.info("-" * 100)

    for i in range(len(TEST_CLUSTERS)):
        cluster_id = TEST_CLUSTERS[i]["cluster_id"]

        # Find corresponding results
        tfidf_topic = next((t for t in tfidf_results if t['cluster_id'] == cluster_id), None)
        keybert_topic = next((t for t in keybert_results if t['cluster_id'] == cluster_id), None)

        logger.info(f"\n📌 Cluster {cluster_id}:")
        logger.info(f"   Original titles:")
        for article in TEST_CLUSTERS[i]["representative_articles"]:
            logger.info(f"   - {article['title']}")

        logger.info(f"\n   {'TF-IDF Topic:':^50} | {'KeyBERT Topic:':^50}")

        tfidf_title = tfidf_topic['topic_title'] if tfidf_topic else "N/A"
        keybert_title = keybert_topic['topic_title'] if keybert_topic else "N/A"

        logger.info(f"   {tfidf_title:^50} | {keybert_title:^50}")

        logger.info(f"\n   {'TF-IDF Keywords:':^50} | {'KeyBERT Keywords:':^50}")

        # Print keywords
        max_keywords = max(
            len(tfidf_topic['keywords']) if tfidf_topic else 0,
            len(keybert_topic['keywords']) if keybert_topic else 0
        )

        for j in range(max_keywords):
            tfidf_kw = ""
            keybert_kw = ""

            if tfidf_topic and j < len(tfidf_topic['keywords']):
                kw = tfidf_topic['keywords'][j]
                tfidf_kw = f"{kw['keyword']} ({kw['score']:.3f})"

            if keybert_topic and j < len(keybert_topic['keywords']):
                kw = keybert_topic['keywords'][j]
                keybert_kw = f"{kw['keyword']} ({kw['score']:.3f})"

            logger.info(f"   {tfidf_kw:^50} | {keybert_kw:^50}")

        logger.info("-" * 100)


def main():
    """Run comparison test."""
    logger.info("\n" + "=" * 100)
    logger.info("KEYBERT vs TF-IDF COMPARISON TEST")
    logger.info("=" * 100)
    logger.info(f"AI Service URL: {AI_SERVICE_URL}")
    logger.info(f"Test Clusters: {len(TEST_CLUSTERS)}")
    logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 100)

    # Test TF-IDF
    logger.info("\n[1/2] Testing TF-IDF method...")
    tfidf_success, tfidf_results, tfidf_time = test_method("tfidf", use_phrases=True)

    if not tfidf_success:
        logger.error("TF-IDF test failed. Aborting.")
        return 1

    logger.info(f"✅ TF-IDF completed in {tfidf_time}s")

    # Test KeyBERT
    logger.info("\n[2/2] Testing KeyBERT method...")
    keybert_success, keybert_results, keybert_time = test_method("keybert")

    if not keybert_success:
        logger.error("KeyBERT test failed.")
        return 1

    logger.info(f"✅ KeyBERT completed in {keybert_time}s")

    # Print comparison
    print_comparison(tfidf_results, keybert_results, tfidf_time, keybert_time)

    # Summary
    logger.info("\n" + "=" * 100)
    logger.info("ANALYSIS")
    logger.info("=" * 100)
    logger.info(f"✅ TF-IDF: {tfidf_time}s processing time")
    logger.info(f"✅ KeyBERT: {keybert_time}s processing time")
    logger.info(f"⚡ Speed difference: {abs(tfidf_time - keybert_time):.2f}s")

    if tfidf_time < keybert_time:
        logger.info(f"   → TF-IDF is {keybert_time/tfidf_time:.1f}x faster")
    else:
        logger.info(f"   → KeyBERT is {tfidf_time/keybert_time:.1f}x faster")

    logger.info("\n💡 Quality Assessment:")
    logger.info("   Please manually review the topics above to determine which method")
    logger.info("   produces more natural and accurate topic titles for Korean news.")
    logger.info("=" * 100)

    return 0


if __name__ == "__main__":
    sys.exit(main())
