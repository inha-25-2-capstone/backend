# Political News Backend

Backend service for Korean political news aggregation and analysis system.

## 🚀 Features

- **News Scraping**: Automated scraping from 6 major Korean news sources (1시간 주기) ⭐
- **AI Processing**: Summarization + 768-dim embedding (Title+Summary) via HF Spaces ⭐
- **BERTopic Clustering**: Backend sklearn clustering with pre-computed embeddings ⭐
- **Real Cosine Similarity**: Article-topic similarity calculation (0.33-0.93 range) ⭐
- **Topic Centroids**: Stored in DB for ranking and recommendation ⭐
- **1시간 파이프라인**: Scraping → AI Processing → BERTopic (Celery Chain) ⭐
- **Database**: PostgreSQL with pgvector extension for similarity search
- **Task Queue**: Celery + Redis for async processing
- **Migrations**: Alembic for version-controlled schema management

## 📋 Tech Stack

- **Python 3.12** with virtual environment
- **FastAPI 0.119.0** - REST API framework (TODO)
- **PostgreSQL 16** + **pgvector** - Vector database
- **Redis** - Task queue & caching
- **Celery** - Async task processing
- **Selenium 4.35.0** - Web scraping
- **scikit-learn** - ML clustering
- **Alembic 1.13.2** - Database migrations

## 🏗️ Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Scraper   │────▶│  PostgreSQL  │◀────│   Celery    │
│  (Naver)    │     │  + pgvector  │     │   Worker    │
└─────────────┘     └──────────────┘     └──────┬──────┘
                            │                    │
                            │                    ▼
                            │            ┌──────────────┐
                            │            │ AI Service   │
                            │            │ (HF Spaces)  │
                            │            └──────────────┘
                            ▼
                    ┌──────────────┐
                    │   FastAPI    │
                    │ (TODO)       │
                    └──────────────┘
```

## 📊 Data Pipeline

### 1시간 주기: Full Pipeline ⭐
1. **Scraping** (Synchronous) → Collect news from 6 sources → DB
2. **Celery Chain**:
   - **AI Processing** (Celery Task) → Summary + Embedding (Title+Summary, 768-dim) → DB
     - Batch size: 50 articles
     - HF Spaces warmup handling
   - **BERTopic Clustering** (Celery Task, Backend) → sklearn clustering with DB embeddings → Save topics ⭐
     - CustomTokenizer for Korean text
     - CountVectorizer + c-TF-IDF
     - Auto topic detection (min_topic_size=5)
     - **Calculate topic centroids** (mean of article embeddings) ⭐
     - **Calculate real cosine similarity** (article ↔ centroid) ⭐
     - Save centroid_embedding and similarity_scores to DB ⭐

### TODO
3. **Stance Analysis** (Celery Task) → Topic-based 옹호/중립/비판 classification
4. **API Serving** → FastAPI endpoints for frontend

## 🛠️ Setup

### Prerequisites

- Python 3.12+
- Docker & Docker Compose
- PostgreSQL 16
- Redis

### Installation

```bash
# 1. Navigate to backend directory
cd backend

# 2. Create virtual environment
python3.12 -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your settings

# 5. Start Docker services
docker compose up -d

# 6. Initialize database
python scripts/init_db.py

# 7. Verify setup
docker compose ps
python scripts/migrate.py current
```

## 🧪 Running Locally

```bash
# Terminal 1: Start Celery worker
celery -A src.workers.celery_app worker --loglevel=info

# Terminal 2: Run 1시간 pipeline (scraping + AI + BERTopic) ⭐
python scripts/run_full_pipeline.py

# OR run components manually:

# Terminal 2a: Run scraper only
python scripts/run_scraper.py

# Terminal 2b: Process articles with AI
python scripts/process_all_articles.py

# Terminal 3: Start FastAPI (TODO)
# uvicorn src.api.main:app --reload --port 8000
```

## 📁 Project Structure

```
backend/
├── src/
│   ├── api/                    # FastAPI application (TODO)
│   ├── scrapers/               # Naver News scraper ✅
│   ├── workers/                # Celery tasks ✅
│   ├── services/               # Business logic ✅
│   │   ├── bertopic_service.py # BERTopic clustering (backend) ⭐
│   │   └── ai_client.py        # AI service client
│   ├── models/                 # Database layer ✅
│   ├── utils/                  # Utilities ✅
│   └── config.py               # Configuration ✅
│
├── database/
│   ├── migrations/             # Alembic migrations ✅
│   └── postgre_schema.sql      # Schema reference
│
├── scripts/                    # Executable scripts ✅
│   ├── run_full_pipeline.py    # 1시간 pipeline ⭐
│   ├── run_scraper.py          # Scraper only
│   ├── process_all_articles.py # Batch AI processing
│   ├── init_db.py              # Database initialization
│   └── migrate.py              # Migration helper
│
├── test_ai_pipeline.py         # End-to-end test ✅
├── docker-compose.yml          # Local development
├── render.yaml                 # Render deployment
├── requirements.txt            # Dependencies
└── alembic.ini                 # Alembic config
```

## 🗄️ Database Schema

### Core Tables

1. **press** - News organizations (6 sources)
2. **article** - Full content + summary + embedding (768-dim from Title+Summary) ⭐
3. **topic** - Daily topics from BERTopic clustering + centroid_embedding ⭐
4. **topic_article_mapping** - Article-to-topic assignments with real similarity scores (0.33-0.93) ⭐
5. **stance_analysis** - 옹호/중립/비판 classification (TODO)
6. **recommended_article** - Top 3 per stance (TODO)

### Key Features

- **pgvector extension**: Vector similarity search
- **Alembic migrations**: Version-controlled schema
- **Embeddings**: From "Title + Summary" for BERTopic consistency ⭐
- **Centroids**: Each topic has centroid_embedding for ranking ⭐
- **Real Similarity**: Cosine similarity scores (not hardcoded) ⭐

## 🔧 Database Migrations

```bash
# Apply all pending migrations
python scripts/migrate.py up

# Create new migration
alembic revision -m "description"

# Check current version
python scripts/migrate.py current

# View history
python scripts/migrate.py history

# Rollback one version
python scripts/migrate.py down

# Reset database (⚠️ destroys all data)
python scripts/migrate.py reset
```

## 📝 Common Commands

```bash
# Run 1시간 pipeline (recommended) ⭐
python scripts/run_full_pipeline.py

# Run scraper only
python scripts/run_scraper.py

# Process articles with AI
python scripts/process_all_articles.py

# Start Celery worker
celery -A src.workers.celery_app worker --loglevel=info

# Run tests
pytest tests/

# Code formatting
black src/

# Linting
flake8 src/
```

## 🌐 Environment Variables

### Required

- `DB_HOST` - PostgreSQL host (default: localhost)
- `DB_PORT` - PostgreSQL port (default: 5432)
- `DB_NAME` - Database name
- `DB_USER` - Database user
- `DB_PASSWORD` - Database password
- `REDIS_URL` - Redis connection URL
- `AI_SERVICE_URL` - AI service endpoint

### Optional (BERTopic Clustering) ⭐

- `BERTOPIC_MIN_TOPIC_SIZE` - Minimum articles per topic (default: 5)
- `BERTOPIC_NR_TOPICS` - Number of topics (default: "auto")
- `BERTOPIC_TOP_N_WORDS` - Keywords per topic (default: 10)

## 🚢 Deployment (Render)

### Prerequisites

1. Render account
2. PostgreSQL instance (with pgvector)
3. Redis instance
4. AI service deployed (HF Spaces)

### Steps

```bash
# 1. Push to GitHub
git add .
git commit -m "Deploy backend"
git push origin main

# 2. In Render Dashboard:
#    - New → Blueprint
#    - Connect GitHub repository
#    - Render reads backend/render.yaml
#    - Configure environment variables
#    - Deploy

# 3. Migrations run automatically
#    (via buildCommand in render.yaml)
```

### Render Services

- **Web Service**: FastAPI backend (TODO)
- **Background Worker**: Celery worker
- **Cron Job**:
  - **1시간 주기**: Full Pipeline (Scraping → AI → BERTopic → Stance) ⭐

## 📊 Current Status (2025-11-12)

### 📈 Recent Verification

- **Articles Processed**: 200 articles with embeddings
- **AI Processing**: Batch size 50, ~30-50s per batch
- **Topics Created**: 8 topics for 2025-11-11
  1. 대장동 항소 포기 (82 articles, avg similarity: 0.649)
  2. 대통령은 11일 국무회의에서 (28 articles, avg similarity: 0.673)
  3. tf 12 공직자 (25 articles, avg similarity: 0.706)
  4. 의원은 미국 인도 (19 articles, avg similarity: 0.543)
  5. 암표 3법 과징금 (12 articles, avg similarity: 0.699)
  6. 오세훈 종묘 15 (9 articles, avg similarity: 0.767)
  7. kis 협약기업 북한 (6 articles, avg similarity: 0.723)
  8. 중국 다이빙 주한중국대사는 (6 articles, avg similarity: 0.882)

- **Similarity Scores**:
  - Range: 0.33 - 0.93 (real cosine similarity, not hardcoded) ⭐
  - All topics have centroid_embedding stored ⭐
  - Average similarity per topic varies (0.54 - 0.88) ⭐

### ✅ Completed Phases

**Backend**:
- ✅ Phase 1: News Collection (Scraper + DB integration)
- ✅ Phase 2: Backend-AI Integration (Celery + AI client with HF Spaces warmup)
- ✅ Phase 3: BERTopic Clustering (sklearn backend with Title+Summary embeddings) ⭐
  - ✅ Real cosine similarity calculation (article ↔ topic centroid) ⭐
  - ✅ Topic centroids stored in DB (for ranking/recommendation) ⭐
  - ✅ Verified: 0.33-0.93 similarity range (2025-11-11, 8 topics) ⭐
- ✅ 1시간 Pipeline (Scraping → AI → BERTopic with Similarity) ⭐
- ✅ Database Migrations (Alembic)

**Frontend** (in front/ folder):
- ✅ Project setup (Vite + React 19 + TypeScript)
- ✅ Component architecture (Common, Layout, Article, Topic, Press, Dashboard)
- ✅ Pages structure (MainPage, TopicDetailPage, ArticleDetailPage, etc.)
- ✅ TanStack Query hooks and API services
- ✅ TypeScript types and Mock data
- ✅ CI/CD pipeline (GitHub Actions)

### 🚧 In Progress

- None

### 📋 TODO (Next Priority)

- ⏭️ Phase 4: Stance Analysis (waiting for ML model)
- ⏭️ **Phase 5: FastAPI Endpoints (HIGH PRIORITY)**
  - `GET /health` - Health check
  - `GET /api/topics` - Topic list (Top 7 for main page)
  - `GET /api/topics/{topic_id}` - Topic detail
  - `GET /api/topics/{topic_id}/articles` - Articles by topic (with stance filter)
  - `GET /api/articles` - All articles (with filters)
  - `GET /api/articles/{article_id}` - Article detail
  - `GET /api/press` - Press list
  - `GET /api/press/{press_id}/articles` - Articles by press
  - `GET /api/topics/{topic_id}/recommendations` - Recommended articles (top 3 per stance)
- ⏭️ Recommendation Engine (top 3 per stance)
- ⏭️ Frontend Integration

## 🧪 Testing

### Unit Tests

```bash
pytest tests/
```

### Integration Tests

```bash
# End-to-end pipeline test
python test_ai_pipeline.py
```

### Manual Testing

```bash
# Test scraper
python scripts/run_scraper.py

# Test AI processing
python scripts/process_all_articles.py

# Test full pipeline
python scripts/run_full_pipeline.py
```

## 🐛 Troubleshooting

### Docker Issues

```bash
# Reset Docker
docker compose down -v
docker compose up -d
```

### Database Connection

```bash
# Check PostgreSQL
docker compose ps
docker compose logs postgres

# Test connection
psql postgresql://postgres:postgres@localhost:5432/politics_news_dev
```

### Redis Connection

```bash
# Check Redis
docker compose ps
redis-cli -h localhost -p 6379 ping
```

### Migration Issues

```bash
# Check migration status
python scripts/migrate.py current

# Reset database (⚠️ destroys data)
python scripts/migrate.py reset
python scripts/init_db.py
```

## 📚 Resources

- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [Celery Docs](https://docs.celeryq.dev/)
- [pgvector Docs](https://github.com/pgvector/pgvector)
- [Alembic Docs](https://alembic.sqlalchemy.org/)
- [Render Docs](https://render.com/docs)

## 📄 License

MIT

## 👥 Team

- Backend Developer: Scraper, API, Celery, deployment
- Frontend Developer: React application (front/ folder) ✅
- ML Engineer: Stance analysis model (Colab)

---

**AI Service**: https://zedwrkc-news-stance-detection.hf.space
