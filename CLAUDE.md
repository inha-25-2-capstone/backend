# CLAUDE.md

Backend development guide for Political News Aggregation System.

## Project Overview

**Political News Aggregation and Analysis Backend** - Scrapes Korean political news, performs AI-powered summarization and embedding generation, clusters by topic with BERTopic, and provides multi-perspective recommendations (옹호/중립/비판).

**Architecture**: Hybrid cloud - Render (backend + BERTopic) + HF Spaces (AI service) + Redis (task queue)

**Current Status (2025-11-18)**:
- ✅ BERTopic clustering with Title+Summary embeddings ⭐
- ✅ Real cosine similarity calculation (article ↔ topic centroid) ⭐
- ✅ Topic centroids stored in DB for ranking ⭐
- ✅ 1시간 파이프라인 (Scraping → AI → BERTopic with Similarity) ⭐
- ✅ Backend-based clustering (sklearn BERTopic) ⭐
- ✅ Verified: 0.33-0.93 similarity range (8 topics) ⭐
- ✅ **FastAPI endpoints** (Health, Topics, Articles, Press) ⭐
- ✅ **BERTopic Visualization API** (DataMapPlot with Korean font support) ⭐
- ✅ **API testing** completed with real data (1,041 articles, 8 topics) ⭐
- ✅ **Production optimizations** (Scraper retry logic, Celery concurrency control, Redis pool limit) ⭐
- ✅ Frontend structure (React 19 + TypeScript + TanStack Query in front/ folder) ⭐
- ⏳ Recommendation Engine (next priority)
- ⏳ Stance analysis (model training in progress)

## Technology Stack

- **Backend**: FastAPI 0.119.0, Celery, PostgreSQL 16 + pgvector, Redis
- **AI Service**: Deployed on HF Spaces (https://gaaahee-news-stance-detection.hf.space)
- **Scraping**: Selenium 4.35.0 + BeautifulSoup4
- **Clustering**: BERTopic 0.17.3 (sklearn-based, backend) ⭐
- **Visualization**: DataMapPlot 0.4.1 + matplotlib 3.9.3 (Korean font: NanumGothic) ⭐
- **Database Migrations**: Alembic 1.13.2
- **Python**: 3.12

## Project Structure

```
backend/
├── src/
│   ├── api/                      # FastAPI application ✅
│   │   ├── main.py               # FastAPI app with CORS
│   │   ├── routes/               # API routes (Health, Topics, Articles, Press)
│   │   │   ├── __init__.py
│   │   │   ├── health.py
│   │   │   ├── topics.py
│   │   │   ├── articles.py
│   │   │   └── press.py
│   │   └── schemas/              # Pydantic models
│   │       ├── __init__.py
│   │       ├── common.py         # Common schemas (Pagination, Stance, etc.)
│   │       └── responses.py      # Response models
│   ├── scrapers/                 # Naver News scraper ✅
│   │   └── scraper.py
│   ├── workers/                  # Celery tasks ✅
│   │   ├── celery_app.py
│   │   └── tasks.py              # AI processing + BERTopic clustering tasks
│   ├── services/                 # Business logic ✅
│   │   ├── ai_client.py          # AI service client (summary + embedding)
│   │   └── bertopic_service.py   # BERTopic clustering + visualization (sklearn + DataMapPlot) ⭐
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
│   ├── run_full_pipeline.py      # 1시간 pipeline (scraping+AI+BERTopic) ⭐
│   ├── run_api.py                # API server startup ✅
│   ├── run_scraper.py            # News collection only
│   ├── process_all_articles.py   # Batch AI processing
│   ├── init_db.py                # Database initialization
│   └── migrate.py                # Migration management
├── requirements.txt
├── alembic.ini
├── docker-compose.yml            # Local development (PostgreSQL + Redis)
└── render.yaml                   # Deployment config
```

## Database Schema (Key Tables)

1. **press** - 6 news organizations
2. **article** - Full content + summary + embedding(768-dim vector from Title+Summary) ⭐
3. **topic** - Daily topics from BERTopic clustering + centroid_embedding ⭐
4. **topic_article_mapping** - Many-to-many with real similarity_score (0.33-0.93) ⭐
5. **stance_analysis** - 옹호/중립/비판 classification (TODO)
6. **recommended_article** - Top 3 per stance per topic (TODO)

**Key Features:**
- pgvector extension for embedding storage
- Embeddings from Title + Summary (not just summary) ⭐
- Real cosine similarity scores (not hardcoded) ⭐
- Topic centroids for ranking and recommendation ⭐
- KST timezone (5:00 AM news cycle cutoff)

## Data Pipeline

**Status**: Phase 1-4 Complete ✅ | Phase 5-6 TODO

```
1시간 주기: 스크래핑 + AI + BERTopic ⭐

Phase 1: News Collection (Synchronous) ✅
Naver News → Selenium Scraper → PostgreSQL (article table)
            ↓
Phase 2: AI Processing (Celery Task) ✅
   POST /batch-process-articles to AI Service (HF Spaces)
   ├─ Input: {article_id, title, content}  ⭐ title 추가
   ├─ Output: {summary, embedding(768-dim from title+summary)}  ⭐
   ├─ Warmup: HF Spaces cold start handling (60s timeout)
   ├─ Batch size: 50 articles
   └─ Save to DB: UPDATE article SET summary, embedding
            ↓
Phase 3: BERTopic Clustering (Celery Task, Backend) ⭐ ✅
   Fetch embeddings from DB → sklearn BERTopic clustering
   ├─ Input: Stored embeddings (768-dim)
   ├─ CustomTokenizer for Korean text (regex-based)
   ├─ CountVectorizer + c-TF-IDF
   ├─ Auto topic detection (min_topic_size=5)
   ├─ Calculate topic centroids (mean of embeddings) ⭐
   ├─ Calculate real cosine similarity (article ↔ centroid) ⭐
   └─ Save to DB: topic (with centroid), topic_article_mapping (with similarity) ⭐
            ↓
Phase 4: FastAPI Endpoints ⭐ ✅
   Health, Topics, Articles, Press APIs
   ├─ Pydantic schemas with Optional stance fields
   ├─ CORS configuration for frontend
   ├─ Pagination support
   └─ API testing completed (1,041 articles, 8 topics, 6 press)

Phase 5: Stance Analysis (TODO - when model ready)
Title + Summary → Stance model → 옹호/중립/비판

Phase 6: Recommendations (TODO)
Top 3 articles per stance using similarity scores
```

## AI Service Integration

**Deployed URL**: https://gaaahee-news-stance-detection.hf.space

**Key Endpoint**: `POST /batch-process-articles`
- Input: List of {article_id, title, content} ⭐ title 추가
- Output: {summary, embedding(768-dim from title+summary)} ⭐
- Batch size: Up to 50 articles
- **Client Timeout**: 240 seconds (increased for reliability) ⭐
- **Warmup**: Automatic HF Spaces cold start handling (60s timeout, 3 retries)

**Key Change**: Embedding now generated from "Title + Summary" instead of just "Summary" ⭐

**Documentation**: https://gaaahee-news-stance-detection.hf.space/docs

## Environment Configuration

### Local (.env)
```bash
DB_HOST=localhost
DB_PORT=5432
DB_NAME=politics_news_dev
DB_USER=postgres
DB_PASSWORD=postgres

REDIS_URL=redis://localhost:6379/0

AI_SERVICE_URL=https://gaaahee-news-stance-detection.hf.space
AI_SERVICE_TIMEOUT=240  # Increased for reliability ⭐
```

### Production (Render Dashboard)
```bash
DATABASE_URL=<auto-injected>
REDIS_URL=<auto-injected>
AI_SERVICE_URL=https://gaaahee-news-stance-detection.hf.space
AI_SERVICE_TIMEOUT=240  # Set in render.yaml ⭐
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
celery -A src.workers.celery_app worker --loglevel=info --concurrency=4  # 4 workers for optimal performance ⭐

# 5. Run 1시간 pipeline (recommended) ⭐
python scripts/run_full_pipeline.py

# 6. Run API server (in separate terminal) ⭐
python scripts/run_api.py  # Runs on http://localhost:8000

# OR run components manually:

# 7a. Run scraper only
python scripts/run_scraper.py

# 7b. Process articles with AI
python scripts/process_all_articles.py
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

## Important Notes

### Three-Stance System
- **옹호** (Support/Positive)
- **중립** (Neutral)
- **비판** (Criticism/Negative)

### Daily News Cycle
- Uses KST 5:00 AM cutoff for `news_date`
- Articles published before 5 AM belong to previous day's cycle

### Scraper
- 6 press companies configured
- Content validation: Min 20 characters
- Duplicate checking by URL
- Auto-enqueues AI processing tasks
- **HTTP Session with Retry**: Max 3 retries with backoff (1s, 2s, 4s) ⭐
- **Timeout**: 30 seconds per article request (increased for reliability) ⭐
- **Connection Pooling**: Reuses HTTP connections for better performance ⭐

### AI Processing
- Celery task: `process_articles_batch(article_ids)`
- Retry logic: Max 3 retries with exponential backoff
- Task timeout: 10 minutes
- Batch size: 50 articles (sent as 5-article batches to HF Spaces)
- **Client Timeout**: 240 seconds (handles slow HF Spaces responses) ⭐
- HF Spaces warmup: Automatic cold start handling
- **Embedding**: Generated from Title + Summary (768-dim) ⭐
- Stance field: Currently `null` (model not ready)

### Celery Worker Configuration ⭐
- **Concurrency**: 4 workers (prevents HF Spaces overload)
- **Prefetch Multiplier**: 1 (process one task at a time)
- **Max Tasks Per Child**: 50 (restart worker after 50 tasks)
- **Redis Connection Pool**: 10 connections (prevents Redis "max clients" error)
- **Broker Retry**: Enabled on startup failures

### BERTopic Clustering ⭐
- **Location**: Backend (not HF Spaces)
- **Algorithm**: sklearn BERTopic with CustomTokenizer
- **Input**: Pre-computed embeddings from DB
- **Frequency**: Every 1 hour (after AI processing)
- **Min topic size**: 5 articles
- **Tokenizer**: Regex-based Korean text processing
- **Similarity**: Real cosine similarity (article ↔ centroid, 0.33-0.93) ⭐
- **Centroids**: Stored in topic.centroid_embedding ⭐
- **Output**: Topic titles from top 3 c-TF-IDF keywords

### 1시간 Pipeline ⭐
- **Cron job**: Runs every hour on Render
- **Steps**:
  1. Scraping (synchronous)
  2. AI Processing (Celery task, batch of 50)
  3. BERTopic Clustering (Celery task, waits for AI completion)
  4. Stance Analysis (TODO)

## Implementation Status

### ✅ Phase 1: News Collection - COMPLETED
- Naver News scraper with 6 press companies
- Database integration with duplicate checking
- KST timezone handling
- Auto-enqueue AI processing tasks

**Files**: `src/scrapers/scraper.py`, `scripts/run_scraper.py`

### ✅ Phase 2: Backend-AI Integration - COMPLETED
- AI Service HTTP client with retry logic
- HF Spaces cold start handling (warmup)
- Celery task for batch AI processing
- Database migration: embedding column (vector 768)
- **Title + Summary embedding** ⭐
- Batch size: 50 articles

**Files**:
- `src/services/ai_client.py` (with warmup logic)
- `src/workers/tasks.py` (process_articles_batch)
- `scripts/process_all_articles.py`

### ✅ Phase 3: BERTopic Clustering - COMPLETED ⭐
- **Backend-based clustering** with sklearn BERTopic
- Fetches pre-computed embeddings from DB
- CustomTokenizer for Korean text (regex-based)
- CountVectorizer + c-TF-IDF
- Auto topic detection (min_topic_size=5)
- **Real cosine similarity calculation** (article ↔ topic centroid) ⭐
- **Topic centroids stored in DB** for ranking/recommendation ⭐
- **Verified**: Similarity scores 0.33-0.93 (2025-11-11, 8 topics) ⭐
- Celery task for automated clustering
- Topics saved to database

**Files**:
- `src/services/bertopic_service.py` (clustering logic + similarity calculation) ⭐
- `src/workers/tasks.py` (bertopic_clustering_task with centroid storage) ⭐

### ✅ Phase 4: FastAPI Endpoints - COMPLETED ⭐
- Health check endpoint
- Topics API (list, detail, articles by topic)
- Articles API (list, detail with multiple filters)
- Press API (list, articles by press)
- **Visualization API** (BERTopic clustering visualization) ⭐
  - GET `/api/topics/visualization` - DataMapPlot PNG image
  - Korean font support (NanumGothic)
  - 1400x1400 px, configurable DPI
  - 1-hour caching (Cache-Control)
- Pydantic schemas with Optional stance fields
- CORS configuration for frontend (ports 5173, 3000)
- Pagination support (offset/limit)
- **API testing completed** (1,041 articles, 8 topics, 6 press) ✅
- Bug fix: NULL topic_rank/cluster_score handling

**Files**:
- `src/api/main.py` (FastAPI app + CORS)
- `src/api/routes/` (health, topics, articles, press)
- `src/api/schemas/` (common, responses)
- `src/services/bertopic_service.py` (visualization function)
- `scripts/run_api.py` (API startup script)

### ⏳ Phase 5: Stance Analysis - TODO
- Fine-tuned stance model deployment (ML Engineer)
- Input: Title + Summary only (no topic information)
- Integrate with AI service
- Save to stance_analysis table

### ⏳ Phase 6: Recommendations - TODO (HIGH PRIORITY)
- Recommendation engine (top 3 per stance per topic)
- Use cosine similarity scores from topic_article_mapping
- Create recommendation endpoint

## Next Steps

**Immediate Priority**: Recommendation Engine

1. Implement recommendation algorithm:
   - Select top 3 articles per stance (support/neutral/oppose)
   - Use cosine similarity scores from topic_article_mapping
   - Consider article quality metrics

2. Create recommendation endpoint:
   - `GET /api/topics/{topic_id}/recommendations`
   - Returns top 3 per stance

**Phase 2 - Stance Analysis Integration** (when model ready):
   - Integrate fine-tuned KoBERT model
   - Add stance prediction to AI processing pipeline
   - Update recommendation logic to use real stance data

**Later**:
1. Frontend-Backend Integration
2. Deployment to Render
3. Performance optimization (caching, query optimization)

## Deployment (Render)

**Prerequisites**: Redis instance, PostgreSQL with pgvector, GitHub connected

**render.yaml** handles:
- Auto-migration on build
- Environment variables
- Service configuration
- Cron jobs (1-hour full pipeline) ⭐
- **Production Optimizations**: ⭐
  - Celery concurrency: 4 workers (prevents HF Spaces overload)
  - AI timeout: 240 seconds (handles slow responses)
  - Redis pool: 10 connections (prevents "max clients" error)

**Manual steps**:
1. Push to GitHub
2. Connect repository in Render Dashboard
3. Configure environment variables (especially `AI_SERVICE_URL` without trailing slash)
4. Deploy

**Production Configuration**:
- **politics-news-api**: Standard plan (2GB RAM for ML libraries)
- **politics-news-worker**: Starter plan (4 workers, 512MB)
- **politics-news-full-pipeline**: Docker runtime (Chromium support)
- **PostgreSQL**: Free plan with pgvector extension
- **Redis**: Free plan (50 connections, 25MB)

---

**For detailed API specs**: See AI service docs at https://gaaahee-news-stance-detection.hf.space/docs

**Current Focus**:
- Backend: FastAPI Endpoints Implementation (Phase 1-3)
- Frontend: Router setup and API integration (in front/ folder)

**Architecture**:
- Backend: 1시간 주기 파이프라인 (Scraping → AI → BERTopic with Similarity) ⭐
- Frontend: React 19 + TypeScript + TanStack Query + Material-UI ⭐
