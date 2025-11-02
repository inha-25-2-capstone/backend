# CLAUDE.md

Backend development guide for Political News Aggregation System.

## Project Overview

**Political News Aggregation and Analysis Backend** - Scrapes Korean political news, performs AI-powered summarization and embedding generation, clusters by topic with incremental assignment, and provides multi-perspective recommendations (옹호/중립/비판).

**Architecture**: Hybrid cloud - Render (backend) + HF Spaces (AI service) + Redis (task queue)

**Current Status (2025-10-22)**:
- ✅ 243 articles collected (5 press sources, excluding Yonhap for testing)
- ✅ 227 articles processed with AI (93% success rate)
- ✅ 7 topics clustered for 2025-10-20
- ✅ Hierarchical clustering (5-10 topics auto) + Centroid-based incremental assignment ⭐
- ✅ 30분 파이프라인 (Scraping → AI → Incremental) ⭐
- ✅ 2시간 리클러스터링 (Hierarchical) ⭐
- ⏳ FastAPI endpoints (next priority)

## Technology Stack

- **Backend**: FastAPI 0.119.0, Celery, PostgreSQL 16 + pgvector, Redis
- **AI Service**: Deployed on HF Spaces (https://zedwrkc-news-stance-detection.hf.space)
- **Scraping**: Selenium 4.35.0 + BeautifulSoup4
- **Clustering**: scikit-learn (Hierarchical, K-Means, DBSCAN), NumPy (cosine similarity)
- **Database Migrations**: Alembic 1.13.2
- **Python**: 3.12

## Project Structure

```
backend/
├── src/
│   ├── api/                      # FastAPI application (TODO)
│   ├── scrapers/                 # Naver News scraper ✅
│   │   └── scraper.py
│   ├── workers/                  # Celery tasks ✅
│   │   ├── celery_app.py
│   │   └── tasks.py
│   ├── services/                 # Business logic ✅
│   │   ├── ai_client.py          # AI service client + HF Spaces warmup
│   │   ├── clustering.py         # Hierarchical/K-Means/DBSCAN + centroid storage ⭐
│   │   └── incremental_assignment.py  # Real-time article assignment
│   ├── models/                   # Database layer ✅
│   │   └── database.py
│   └── utils/
│       └── logger.py
├── database/
│   ├── postgre_schema.sql
│   └── migrations/               # Alembic migrations ✅
│       └── versions/
│           ├── 1fdac3e26595_initial_schema.py
│           ├── 50f79b54aace_add_embedding_column.py
│           └── 6659f7177381_add_centroid_pending.py
├── scripts/
│   ├── run_scraper_with_pipeline.py  # 30분 pipeline (scraping+AI+incremental) ⭐
│   ├── run_scraper.py            # News collection only
│   ├── run_clustering.py         # Topic clustering (hierarchical) ⭐
│   ├── incremental_assign.py     # Incremental assignment
│   ├── process_all_articles.py   # Batch AI processing (excludes Yonhap)
│   ├── init_db.py                # Database initialization
│   └── migrate.py                # Migration management
├── test_ai_pipeline.py           # Pipeline test ✅
├── requirements.txt
├── alembic.ini
├── docker-compose.yml            # Local development (PostgreSQL + Redis)
└── render.yaml                   # Deployment config
```

## Database Schema (Key Tables)

1. **press** - 6 news organizations (currently using 5, excluding Yonhap for testing)
2. **article** - Full content + summary + embedding(768-dim vector)
   - 243 articles total
   - 227 with AI processing completed
3. **topic** - Daily top 7 trending topics
   - Includes centroid_embedding for incremental assignment
   - 7 topics for 2025-10-20
4. **topic_article_mapping** - Many-to-many with similarity_score
5. **pending_articles** - Articles below similarity threshold
6. **stance_analysis** - 옹호/중립/비판 classification (TODO)
7. **recommended_article** - Top 3 per stance per topic (TODO)

**Key Features:**
- pgvector extension for embedding storage
- IVFFlat index for cosine similarity search
- KST timezone (5:00 AM news cycle cutoff)

## Data Pipeline

**Status**: Phase 1-3.5 Complete ✅ | Phase 4-5 TODO

```
30분 주기: 스크래핑 + 파이프라인 ⭐
Phase 1: News Collection
Naver News → Selenium Scraper → PostgreSQL (article table)
            ↓
Phase 2: Celery Chain Trigger (Automatic)
   ├─> AI Processing (Celery Worker)
   │   ├─ POST /batch-process-articles to AI Service (HF Spaces)
   │   ├─ Input: {article_id, content}
   │   ├─ Output: {summary, embedding(768-dim), stance(optional)}
   │   ├─ Warmup: HF Spaces cold start handling (60s timeout)
   │   ├─ Batch size: 5 articles (configurable)
   │   └─ Save to DB: UPDATE article SET summary, embedding
   │
   └─> Incremental Assignment (Automatic)
       ├─ Compare with topic centroids
       ├─ Similarity threshold: 0.5
       ├─ Centroid update weight: 0.1
       └─ O(n) complexity vs O(n²) re-clustering

2시간 주기: Full Re-Clustering ⭐
Phase 3: Hierarchical Clustering
Use stored embeddings → Hierarchical (distance_threshold=0.5)
  ├─ Auto-range: 5-10 topics
  ├─ Save top 7 topics
  ├─ Centroid embedding storage
  ├─ Representative article selection
  └─ Silhouette score evaluation

Phase 4: Stance Analysis (TODO - when model ready)
Summary → Stance model → 옹호/중립/비판

Phase 5: API & Recommendations (TODO)
FastAPI endpoints → Frontend
```

## AI Service Integration

**Deployed URL**: https://zedwrkc-news-stance-detection.hf.space

**Key Endpoint**: `POST /batch-process-articles`
- Input: List of {article_id, content}
- Output: {summary, embedding(768-dim), stance(optional)}
- Batch size: Up to 50 articles (currently using 5 for testing)
- Timeout: 120 seconds
- **Warmup**: Automatic HF Spaces cold start handling (60s timeout, 3 retries)

**Improvements Made**:
- ✅ Warmup logic for HF Spaces cold start
- ✅ Automatic retry with exponential backoff
- ✅ Session persistence for multiple batches
- ✅ Configurable batch sizes

**Documentation**: https://zedwrkc-news-stance-detection.hf.space/docs

## Environment Configuration

### Local (.env)
```bash
DB_HOST=localhost
DB_PORT=5432
DB_NAME=politics_news_dev
DB_USER=postgres
DB_PASSWORD=postgres

REDIS_URL=redis://localhost:6379/0

AI_SERVICE_URL=https://zedwrkc-news-stance-detection.hf.space
AI_SERVICE_TIMEOUT=120

# Clustering (Hierarchical) ⭐
CLUSTERING_ALGORITHM=hierarchical
CLUSTERING_DISTANCE_THRESHOLD=0.5
CLUSTERING_MIN_TOPICS=5
CLUSTERING_MAX_TOPICS=10
CLUSTERING_TOP_N=7

# Incremental Assignment
INCREMENTAL_SIMILARITY_THRESHOLD=0.5
INCREMENTAL_CENTROID_UPDATE_WEIGHT=0.1
```

### Production (Render Dashboard)
```bash
DATABASE_URL=<auto-injected>
REDIS_URL=<auto-injected>
AI_SERVICE_URL=https://zedwrkc-news-stance-detection.hf.space
AI_SERVICE_TIMEOUT=120

# Clustering (Hierarchical) ⭐
CLUSTERING_ALGORITHM=hierarchical
CLUSTERING_DISTANCE_THRESHOLD=0.5
CLUSTERING_MIN_TOPICS=5
CLUSTERING_MAX_TOPICS=10
CLUSTERING_TOP_N=7

# Incremental Assignment
INCREMENTAL_SIMILARITY_THRESHOLD=0.5
INCREMENTAL_CENTROID_UPDATE_WEIGHT=0.1
```

## Local Development Quick Start

```bash
# 1. Setup
cd backend
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Edit with local settings

# 2. Start services
docker compose up -d  # PostgreSQL + Redis

# 3. Initialize database
python scripts/init_db.py

# 4. Start Celery worker (in separate terminal)
celery -A src.workers.celery_app worker --loglevel=info

# 5. Run 30분 pipeline (recommended) ⭐
python scripts/run_scraper_with_pipeline.py

# OR run components manually:

# 6a. Run scraper only
python scripts/run_scraper.py

# 6b. Process articles with AI
python scripts/process_all_articles.py  # Excludes Yonhap

# 6c. Run clustering (hierarchical) ⭐
python scripts/run_clustering.py 2025-10-20 hierarchical

# 6d. Run incremental assignment
python scripts/incremental_assign.py --date 2025-10-20

# 7. Test pipeline
python test_ai_pipeline.py
```

## Database Migrations

```bash
# Apply migrations
python scripts/migrate.py up

# Create new migration
alembic revision -m "description"

# Check current version
python scripts/migrate.py current

# Rollback one version
python scripts/migrate.py down
```

## Current Test Data

**Articles (243 total)**:
- YTN (052): 99 articles
- SBS (020): 47 articles
- 경향신문 (032): 47 articles
- 한겨레 (028): 27 articles
- 조선일보 (023): 23 articles
- ~~연합뉴스 (001)~~: Excluded for testing

**Topics (7 for 2025-10-20)**:
1. 국정감사 '김현지 공방' (104 articles)
2. 재판소원 당론 추진 (66 articles)
3. 주택시장 안정 (56 articles)
4. 캄보디아 감금 사건 (56 articles)
5. 윤 대통령 면회 논란 (52 articles)
6. 방산·항공우주 투자 (46 articles)
7. 남북한 통일 여론조사 (20 articles)

**AI Processing**:
- Success rate: 93% (227/243)
- Failed: 16 articles (AI model "index out of range" errors)
- Average processing time: 30-50s per batch (5 articles)

## Important Notes

### Three-Stance System
- **옹호** (Support/Positive)
- **중립** (Neutral)
- **비판** (Criticism/Negative)

### Daily News Cycle
- Uses KST 5:00 AM cutoff for `news_date`
- Articles published before 5 AM belong to previous day's cycle

### Scraper
- 6 press companies configured: 연합뉴스, SBS, 조선일보, 한겨레, 경향신문, YTN
- Currently excluding Yonhap (press_id='001') for testing
- Content validation: Min 20 characters
- Duplicate checking by URL
- Auto-enqueues AI processing tasks

### AI Processing
- Celery task: `process_articles_batch(article_ids)`
- Retry logic: Max 3 retries with exponential backoff
- Task timeout: 10 minutes
- Batch size: 5 articles (configurable via scripts/process_all_articles.py)
- HF Spaces warmup: Automatic cold start handling
- Stance field: Currently `null` (model not ready)

### Clustering ⭐
- Algorithm: Hierarchical (default), K-Means, DBSCAN
- Distance threshold: 0.5 (auto-adjusts 5-10 topics)
- Saved topics: Top 7
- Quality metric: Silhouette score
- Centroid storage: For incremental assignment
- Re-clustering: Every 2 hours (Render Cron)

### Incremental Assignment
- Frequency: Every 30 minutes (part of scraping pipeline) ⭐
- Similarity threshold: 0.5 (cosine similarity)
- Centroid update: Exponential moving average (weight=0.1)
- Pending articles: Below threshold, wait for re-clustering

### 30분 Pipeline ⭐
- Scraping → AI Processing → Incremental Assignment (Celery Chain)
- Batch size: 5 articles
- Fully automated via Render Cron

## Current Implementation Status

### ✅ Phase 1: News Collection - COMPLETED
- Naver News scraper with 6 press companies (5 active for testing)
- Database integration with duplicate checking
- KST timezone handling
- Auto-enqueue AI processing tasks

**Files**: `src/scrapers/scraper.py`, `scripts/run_scraper.py`

### ✅ Phase 2: Backend-AI Integration - COMPLETED
- AI Service HTTP client with retry logic
- HF Spaces cold start handling (warmup)
- Celery task for batch AI processing
- Database migration: embedding column (vector 768)
- Batch size: 5 articles (excludes Yonhap)
- Success rate: 93%

**Files**:
- `src/services/ai_client.py` (with warmup logic)
- `src/workers/tasks.py`
- `scripts/process_all_articles.py` (Yonhap exclusion)

### ✅ Phase 3: Topic Clustering - COMPLETED ⭐
- **Hierarchical clustering** (default) with cosine similarity
- Distance threshold 0.5, auto-range 5-10 topics
- K-Means and DBSCAN also supported (configurable)
- Representative article selection (closest to centroid)
- Silhouette score evaluation
- Celery task for automated clustering
- Top 7 topics saved
- **Centroid storage** for incremental assignment

**Files**:
- `src/services/clustering.py`
- `scripts/run_clustering.py`

**Test Results**:
- 200 articles → 7 topics
- Silhouette score: 0.178
- Largest topic: 104 articles
- Smallest topic: 20 articles

### ✅ Phase 3.5: Incremental Assignment + 30분 Pipeline - COMPLETED ⭐
- Centroid-based article assignment
- Similarity threshold: 0.5
- Pending articles system
- Centroid updating (EMA)
- O(n) complexity vs O(n²) re-clustering
- **30분 pipeline**: Scraping → AI → Incremental (Celery Chain)

**Files**:
- `src/services/incremental_assignment.py` (455 lines)
- `scripts/incremental_assign.py`
- `scripts/run_scraper_with_pipeline.py` ⭐
- `src/workers/tasks.py` (incremental_assign_articles task)

### ⏳ Phase 4: Stance Analysis - WAITING
- Fine-tuned stance model deployment (ML Engineer)
- Integrate with AI service
- Save to stance_analysis table

### ⏳ Phase 5: API & Recommendations - TODO (HIGH PRIORITY)
- FastAPI endpoints for frontend
- Recommendation engine (top 3 per stance)
- CORS configuration
- Deploy to Render

## Next Steps

**Immediate Priority**: FastAPI Endpoints Implementation

1. Create API routes:
   - `backend/src/api/routes/health.py`
   - `backend/src/api/routes/topics.py`
   - `backend/src/api/routes/articles.py`

2. Pydantic schemas:
   - `backend/src/api/schemas/responses.py`

3. Main FastAPI app:
   - `backend/src/api/main.py`
   - CORS middleware
   - Router registration

4. Key endpoints:
   - `GET /health`
   - `GET /api/v1/topics?date=YYYY-MM-DD`
   - `GET /api/v1/topics/{topic_id}/articles`
   - `GET /api/v1/articles/{article_id}`

5. Recommendation engine (top 3 per stance per topic)

6. Deploy to Render

**Later**:
1. Stance analysis integration (when model ready)
2. Frontend integration
3. Performance optimization
4. Re-enable Yonhap News processing

## Deployment (Render)

**Prerequisites**: Redis instance, PostgreSQL with pgvector, GitHub connected

**render.yaml** handles:
- Auto-migration on build
- Environment variables
- Service configuration
- Cron jobs (scraper, clustering, incremental assignment)

**Manual steps**:
1. Push to GitHub
2. Connect repository in Render Dashboard
3. Configure environment variables
4. Deploy

---

**For detailed API specs**: See AI service docs at https://zedwrkc-news-stance-detection.hf.space/docs

**Current Focus**: FastAPI Endpoints Implementation
**Test Data**: 243 articles, 7 topics (excluding Yonhap News)
