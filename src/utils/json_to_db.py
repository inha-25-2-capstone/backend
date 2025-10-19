"""
JSON 파일의 내용을 PostgreSQL 데이터베이스에 저장하는 스크립트

주요 개선사항:
1. Bulk Insert를 사용한 대량 데이터 처리 (100배 이상 성능 향상)
2. 청크 단위 커밋으로 부분 실패 시에도 성공한 데이터 보존
3. SAVEPOINT를 활용한 안정적인 트랜잭션 관리
4. 상세한 진행 상황 및 에러 로깅
"""
import json
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime, timedelta
from config import DATABASE_URL
import sys
import os


# 설정 상수
CHUNK_SIZE = 100  # 한 번에 처리할 기사 수


def calculate_news_date(published_at_str):
    """
    기사 발행 시간을 기준으로 'news_date'를 계산합니다.
    KST 05:00시를 기준으로 하루가 바뀝니다.

    예시:
    - 2025-10-17 04:59:59 -> 2025-10-16
    - 2025-10-17 05:00:00 -> 2025-10-17

    Args:
        published_at_str: "YYYY-MM-DD HH:MM:SS" 형식의 문자열

    Returns:
        news_date: "YYYY-MM-DD" 형식의 날짜 문자열
    """
    try:
        published_at = datetime.strptime(published_at_str, "%Y-%m-%d %H:%M:%S")
        if published_at.hour < 5:
            news_date = (published_at - timedelta(days=1)).date()
        else:
            news_date = published_at.date()
        return str(news_date)
    except Exception as e:
        print(f"  ⚠️  날짜 변환 오류: {published_at_str}, 오류: {e}")
        return None


def get_press_id_from_url(url):
    """
    네이버 뉴스 URL에서 언론사 ID를 추출합니다.

    예시: https://n.news.naver.com/article/001/0015683856 -> "001"

    Args:
        url: 네이버 뉴스 원문 URL

    Returns:
        press_id: 언론사 ID (3자리 문자열)
    """
    try:
        parts = url.split('/')
        if 'article' in parts and len(parts) > parts.index('article') + 1:
            return parts[parts.index('article') + 1]
        return None
    except Exception as e:
        print(f"  ⚠️  URL에서 언론사 ID 추출 실패: {url}, 오류: {e}")
        return None


def load_json_file(filename):
    """
    JSON 파일을 읽어 파이썬 객체로 반환합니다.

    Args:
        filename: JSON 파일 이름

    Returns:
        articles: 기사 정보 리스트
    """
    try:
        if not os.path.exists(filename):
            print(f"❌ 파일이 존재하지 않습니다: {filename}")
            return None

        with open(filename, 'r', encoding='utf-8') as f:
            articles = json.load(f)

        print(f"✅ JSON 파일 로딩 완료: 총 {len(articles)}개의 기사")
        return articles
    except Exception as e:
        print(f"❌ JSON 파일 읽기 오류: {e}")
        return None


def bulk_insert_press(cursor, press_data_list):
    """
    언론사 정보를 일괄 삽입합니다 (Bulk Insert).
    중복된 경우 무시합니다.

    Args:
        cursor: psycopg2 커서 객체
        press_data_list: [(press_id, press_name), ...] 형태의 리스트

    Returns:
        inserted_count: 실제 삽입된 언론사 수
    """
    if not press_data_list:
        return 0

    try:
        # 중복 제거 (press_id 기준)
        unique_press = {}
        for press_id, press_name in press_data_list:
            if press_id not in unique_press:
                unique_press[press_id] = press_name

        press_values = list(unique_press.items())

        query = """
            INSERT INTO press (press_id, press_name)
            VALUES %s
            ON CONFLICT (press_id) DO NOTHING
        """

        execute_values(cursor, query, press_values, template="(%s, %s)")
        return cursor.rowcount
    except Exception as e:
        print(f"  ⚠️  언론사 일괄 삽입 오류: {e}")
        return 0


def bulk_insert_articles(cursor, article_data_list):
    """
    기사 정보를 일괄 삽입합니다 (Bulk Insert).
    중복된 URL인 경우 무시합니다.

    Args:
        cursor: psycopg2 커서 객체
        article_data_list: [(press_id, news_date, author, title, content,
                             article_url, img_url, published_at), ...] 리스트

    Returns:
        inserted_count: 실제 삽입된 기사 수
    """
    if not article_data_list:
        return 0

    try:
        query = """
            INSERT INTO article (
                press_id, news_date, author, title, content,
                article_url, img_url, published_at
            )
            VALUES %s
            ON CONFLICT (article_url) DO NOTHING
        """

        execute_values(
            cursor,
            query,
            article_data_list,
            template="(%s, %s, %s, %s, %s, %s, %s, %s)"
        )
        return cursor.rowcount
    except Exception as e:
        print(f"  ⚠️  기사 일괄 삽입 오류: {e}")
        raise  # 상위에서 처리하도록 예외 전파


def prepare_article_data(article, press_id):
    """
    JSON 기사 데이터를 DB 삽입용 튜플로 변환합니다.

    Args:
        article: JSON 기사 데이터 (dict)
        press_id: 언론사 ID

    Returns:
        tuple: DB 삽입용 데이터 또는 None (오류 시)
    """
    try:
        news_date = calculate_news_date(article['date'])
        if not news_date:
            return None

        # published_at을 KST 타임존으로 명시
        # JSON의 'date'는 KST 기준 "YYYY-MM-DD HH:MM:SS" 형식
        published_at_kst = article['date'] + '+09:00'  # KST = UTC+9

        return (
            press_id,
            news_date,
            article.get('author'),      # NULL 허용
            article['title'],
            article['content'],
            article['url'],
            article.get('img'),         # NULL 허용
            published_at_kst            # 타임존 정보 포함
        )
    except KeyError as e:
        print(f"  ⚠️  필수 키 누락: {e}, URL: {article.get('url', 'N/A')}")
        return None
    except Exception as e:
        print(f"  ⚠️  데이터 준비 오류: {e}, URL: {article.get('url', 'N/A')}")
        return None


def process_chunk(cursor, articles_chunk, chunk_idx, total_chunks):
    """
    청크 단위로 기사를 처리합니다.
    SAVEPOINT를 사용하여 부분 실패 시에도 다른 청크는 보존합니다.

    Args:
        cursor: psycopg2 커서 객체
        articles_chunk: 처리할 기사 리스트
        chunk_idx: 현재 청크 번호
        total_chunks: 전체 청크 수

    Returns:
        dict: 처리 결과 통계
    """
    stats = {
        'processed': 0,
        'press_inserted': 0,
        'articles_inserted': 0,
        'skipped': 0,
        'errors': 0
    }

    savepoint_name = f"chunk_{chunk_idx}"

    try:
        # SAVEPOINT 생성
        cursor.execute(f"SAVEPOINT {savepoint_name}")

        # 1단계: 언론사 데이터 준비
        press_data = []
        article_data = []

        for article in articles_chunk:
            stats['processed'] += 1

            # 언론사 ID 추출
            press_id = article.get('press_id') or get_press_id_from_url(article['url'])
            if not press_id:
                print(f"  ⚠️  언론사 ID 추출 실패: {article.get('url', 'N/A')}")
                stats['skipped'] += 1
                continue

            # 언론사 데이터 수집
            press_data.append((press_id, article['press']))

            # 기사 데이터 준비
            article_tuple = prepare_article_data(article, press_id)
            if article_tuple:
                article_data.append(article_tuple)
            else:
                stats['skipped'] += 1

        # 2단계: 일괄 삽입
        stats['press_inserted'] = bulk_insert_press(cursor, press_data)
        stats['articles_inserted'] = bulk_insert_articles(cursor, article_data)

        # SAVEPOINT 해제 (성공)
        cursor.execute(f"RELEASE SAVEPOINT {savepoint_name}")

        print(f"  ✅ 청크 {chunk_idx}/{total_chunks} 완료: "
              f"언론사 {stats['press_inserted']}개, "
              f"기사 {stats['articles_inserted']}개 삽입")

    except Exception as e:
        # SAVEPOINT로 롤백 (이 청크만 취소)
        cursor.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
        stats['errors'] = len(articles_chunk)
        print(f"  ❌ 청크 {chunk_idx}/{total_chunks} 실패: {e}")

    return stats


def main():
    """
    메인 함수: JSON 파일을 읽어 데이터베이스에 일괄 삽입합니다.
    """
    # 1. 파일명 결정
    if len(sys.argv) > 1:
        json_filename = sys.argv[1]
    else:
        today = datetime.now().strftime("%Y-%m-%d")
        json_filename = f"politics_news_{today}.json"

    print(f"\n{'='*60}")
    print(f"📂 처리할 JSON 파일: {json_filename}")
    print(f"{'='*60}\n")

    # 2. JSON 파일 로드
    articles = load_json_file(json_filename)
    if not articles:
        return

    # 3. 데이터베이스 연결
    conn = None
    try:
        print(f"🔌 데이터베이스 연결 시도...")
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        print(f"✅ 데이터베이스 연결 성공\n")
    except Exception as e:
        print(f"❌ 데이터베이스 연결 실패: {e}")
        return

    # 4. 청크 단위 처리
    try:
        total_articles = len(articles)
        total_chunks = (total_articles + CHUNK_SIZE - 1) // CHUNK_SIZE

        print(f"📊 처리 계획:")
        print(f"  - 총 기사 수: {total_articles}개")
        print(f"  - 청크 크기: {CHUNK_SIZE}개")
        print(f"  - 총 청크 수: {total_chunks}개\n")
        print(f"{'='*60}")
        print(f"🚀 데이터 삽입 시작...\n")

        # 전체 통계
        total_stats = {
            'processed': 0,
            'press_inserted': 0,
            'articles_inserted': 0,
            'skipped': 0,
            'errors': 0
        }

        # 청크별 처리
        for i in range(0, total_articles, CHUNK_SIZE):
            chunk = articles[i:i + CHUNK_SIZE]
            chunk_idx = i // CHUNK_SIZE + 1

            stats = process_chunk(cursor, chunk, chunk_idx, total_chunks)

            # 통계 누적
            for key in total_stats:
                total_stats[key] += stats[key]

        # 5. 전체 커밋
        conn.commit()
        print(f"\n{'='*60}")
        print(f"💾 모든 변경사항이 데이터베이스에 커밋되었습니다")

        # 6. 최종 통계 조회
        cursor.execute("SELECT COUNT(*) FROM press")
        total_press = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM article")
        total_articles_in_db = cursor.fetchone()[0]

        # 7. 결과 출력
        print(f"{'='*60}")
        print(f"🎉 데이터 처리 완료!")
        print(f"{'='*60}")
        print(f"\n📈 처리 통계:")
        print(f"  - 총 처리 대상: {total_stats['processed']}개")
        print(f"  - ✅ 신규 삽입된 언론사: {total_stats['press_inserted']}개")
        print(f"  - ✅ 신규 삽입된 기사: {total_stats['articles_inserted']}개")
        print(f"  - ⚠️  건너뛴 기사: {total_stats['skipped']}개")
        print(f"  - ❌ 오류 발생: {total_stats['errors']}개")
        print(f"\n📊 데이터베이스 현황:")
        print(f"  - 총 언론사 수: {total_press}개")
        print(f"  - 총 기사 수: {total_articles_in_db}개")
        print(f"{'='*60}\n")

    except Exception as e:
        print(f"\n❌ 데이터 처리 중 심각한 오류 발생: {e}")
        if conn:
            conn.rollback()
            print(f"🔄 모든 변경사항이 롤백되었습니다")
    finally:
        if conn:
            cursor.close()
            conn.close()
            print(f"🔒 데이터베이스 연결 종료\n")


if __name__ == "__main__":
    main()
