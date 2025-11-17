import os
from dotenv import load_dotenv

# .env 파일에서 환경 변수 로드
load_dotenv()

# DATABASE_URL이 .env에 이미 정의되어 있으면 그것을 사용
DATABASE_URL = os.getenv("DATABASE_URL")

# DATABASE_URL이 없으면 개별 환경 변수로 조합
if not DATABASE_URL:
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_HOST = os.getenv("DB_HOST")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME")

    # 데이터베이스 연결 URL 구성
    # psycopg2 드라이버를 위한 포맷: postgresql://user:password@host:port/dbname
    DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

    # 환경 변수가 제대로 설정되었는지 확인
    if not all([DB_USER, DB_PASSWORD, DB_HOST, DB_NAME]):
        raise ValueError("환경 변수(DB_USER, DB_PASSWORD, DB_HOST, DB_NAME)가 올바르게 설정되지 않았습니다.")

# DATABASE_URL이 설정되었는지 최종 확인
if not DATABASE_URL:
    raise ValueError("DATABASE_URL이 설정되지 않았습니다.")

# AI Service Configuration
AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "https://gaaahee-news-stance-detection.hf.space")
AI_SERVICE_TIMEOUT = int(os.getenv("AI_SERVICE_TIMEOUT", "120"))

# Redis Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Clustering Configuration
CLUSTERING_ALGORITHM = os.getenv("CLUSTERING_ALGORITHM", "hierarchical")
CLUSTERING_DISTANCE_THRESHOLD = float(os.getenv("CLUSTERING_DISTANCE_THRESHOLD", "0.6"))
CLUSTERING_MIN_TOPICS = int(os.getenv("CLUSTERING_MIN_TOPICS", "5"))
CLUSTERING_MAX_TOPICS = int(os.getenv("CLUSTERING_MAX_TOPICS", "100"))
CLUSTERING_TOP_N = int(os.getenv("CLUSTERING_TOP_N", "10"))

# Incremental Assignment Configuration
INCREMENTAL_SIMILARITY_THRESHOLD = float(os.getenv("INCREMENTAL_SIMILARITY_THRESHOLD", "0.5"))
INCREMENTAL_CENTROID_UPDATE_WEIGHT = float(os.getenv("INCREMENTAL_CENTROID_UPDATE_WEIGHT", "0.1"))

# Pydantic Settings 클래스를 사용하여 환경 변수를 더 안전하게 관리할 수도 있습니다.
# from pydantic_settings import BaseSettings, SettingsConfigDict
# class Settings(BaseSettings):
#     DB_URL: str = "postgresql+psycopg2://user:password@host:5432/db"
#     model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')
# settings = Settings()
# DATABASE_URL = settings.DB_URL