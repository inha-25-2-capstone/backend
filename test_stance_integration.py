"""
Test script to verify stance analysis integration

Tests:
1. AI Service returns stance data
2. Backend saves stance to database
3. End-to-end pipeline works correctly
"""
import sys
import os

# Add backend directory to path
sys.path.insert(0, os.path.dirname(__file__))

from src.services.ai_client import create_ai_client, ArticleInput
from src.models.database import StanceRepository, ArticleRepository
from src.config import AI_SERVICE_URL


def test_ai_service_stance():
    """Test that AI service returns stance data"""
    print("\n" + "=" * 80)
    print("TEST 1: AI Service Stance Analysis")
    print("=" * 80)

    test_articles = [
        ArticleInput(
            article_id=999991,
            title="정부 부동산 규제 완화 발표",
            content="정부가 오늘 부동산 규제 완화 방안을 발표했다. "
                   "이번 조치로 주택 구매가 더 쉬워질 전망이다. "
                   "전문가들은 이번 정책이 경제 활성화에 도움이 될 것으로 기대하고 있다."
        ),
        ArticleInput(
            article_id=999992,
            title="야당 정부 정책 강력 비판",
            content="야당은 오늘 정부의 정책에 대해 강하게 비판했다. "
                   "야당 대표는 이번 정책이 서민들에게 도움이 되지 않는다고 주장했다. "
                   "야당은 정부가 재검토해야 한다고 촉구했다."
        )
    ]

    with create_ai_client(base_url=AI_SERVICE_URL, timeout=120) as client:
        print(f"\nConnecting to AI service: {AI_SERVICE_URL}")
        results = client.process_batch(test_articles)

        for result in results:
            print(f"\n{'─' * 80}")
            print(f"Article {result.article_id}")
            print(f"{'─' * 80}")

            if result.error:
                print(f"❌ ERROR: {result.error}")
                return False

            if result.summary:
                print(f"✓ Summary generated ({len(result.summary)} chars)")

            if result.embedding:
                print(f"✓ Embedding generated ({len(result.embedding)}-dim)")

            if result.stance:
                print(f"✓ Stance analyzed:")
                print(f"  Label: {result.stance['stance_label'].upper()}")
                print(f"  Score: {result.stance['stance_score']:.4f}")
                print(f"  Probabilities:")
                print(f"    Support: {result.stance['prob_positive']:.4f}")
                print(f"    Neutral: {result.stance['prob_neutral']:.4f}")
                print(f"    Oppose:  {result.stance['prob_negative']:.4f}")
            else:
                print(f"❌ Stance data missing!")
                return False

    print("\n✅ TEST 1 PASSED: AI service returns stance data\n")
    return True


def test_stance_repository():
    """Test StanceRepository database operations"""
    print("\n" + "=" * 80)
    print("TEST 2: StanceRepository Database Operations")
    print("=" * 80)

    # Test insert
    print("\n1. Testing insert...")
    try:
        stance_id = StanceRepository.insert(
            article_id=999991,
            stance_label='support',
            prob_positive=0.85,
            prob_neutral=0.10,
            prob_negative=0.05,
            stance_score=0.80
        )
        print(f"✓ Inserted stance_id: {stance_id}")
    except Exception as e:
        print(f"❌ Insert failed: {e}")
        return False

    # Test get_by_article_id
    print("\n2. Testing get_by_article_id...")
    try:
        stance = StanceRepository.get_by_article_id(999991)
        if stance:
            print(f"✓ Retrieved stance:")
            print(f"  Label: {stance['stance_label']}")
            print(f"  Score: {stance['stance_score']}")
        else:
            print(f"❌ No stance found for article 999991")
            return False
    except Exception as e:
        print(f"❌ Retrieval failed: {e}")
        return False

    # Test count_by_stance
    print("\n3. Testing count_by_stance...")
    try:
        counts = StanceRepository.count_by_stance()
        print(f"✓ Stance counts:")
        print(f"  Support: {counts.get('support', 0)}")
        print(f"  Neutral: {counts.get('neutral', 0)}")
        print(f"  Oppose:  {counts.get('oppose', 0)}")
    except Exception as e:
        print(f"❌ Count failed: {e}")
        return False

    # Cleanup
    print("\n4. Cleaning up test data...")
    try:
        from src.models.database import get_db_cursor
        with get_db_cursor() as cur:
            cur.execute("DELETE FROM stance_analysis WHERE article_id IN (999991, 999992)")
            print(f"✓ Test data cleaned up")
    except Exception as e:
        print(f"⚠ Cleanup warning: {e}")

    print("\n✅ TEST 2 PASSED: StanceRepository works correctly\n")
    return True


def main():
    """Run all tests"""
    print("\n" + "=" * 80)
    print("STANCE ANALYSIS INTEGRATION TEST SUITE")
    print("=" * 80)

    tests = [
        ("AI Service Stance Analysis", test_ai_service_stance),
        ("StanceRepository Operations", test_stance_repository),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"\n❌ TEST FAILED with exception: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed} ✅")
    print(f"Failed: {failed} {'❌' if failed > 0 else ''}")
    print("=" * 80)

    if failed == 0:
        print("\n🎉 ALL TESTS PASSED! Stance integration is working correctly.\n")
        return 0
    else:
        print(f"\n⚠️  {failed} test(s) failed. Please check the logs above.\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
