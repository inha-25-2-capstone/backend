DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'stance_type') THEN
        CREATE TYPE stance_type AS ENUM ('옹호', '중립', '비판');
    END IF;
END $$;

-- ========================================
-- 1. 언론사 테이블 (press)
-- ========================================
CREATE TABLE IF NOT EXISTS press (
    press_id VARCHAR(10) PRIMARY KEY,
    press_name VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE press IS '언론사 정보를 저장하는 테이블';
COMMENT ON COLUMN press.press_id IS '네이버 언론사 ID';
COMMENT ON COLUMN press.press_name IS '언론사 이름';
COMMENT ON COLUMN press.created_at IS '데이터 생성 일시';

-- ========================================
-- 2. 기사 테이블 (article)
-- ========================================
CREATE TABLE IF NOT EXISTS article (
    article_id BIGSERIAL PRIMARY KEY,
    press_id VARCHAR(10) NOT NULL,
    news_date DATE NOT NULL,
    author VARCHAR(100),
    title VARCHAR(300) NOT NULL,
    content TEXT NOT NULL,
    summary TEXT,
    article_url VARCHAR(2083) NOT NULL UNIQUE,
    img_url VARCHAR(2083),
    published_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    embedding vector(768),

    -- 외래키
    CONSTRAINT fk_article_press FOREIGN KEY (press_id) REFERENCES press(press_id),
    
    -- 제약조건
    CONSTRAINT chk_published_at CHECK (published_at <= NOW()),
    CONSTRAINT chk_author_not_empty CHECK (author IS NULL OR TRIM(author) != '')
);

COMMENT ON TABLE article IS '뉴스 기사 정보를 저장하는 테이블';
COMMENT ON COLUMN article.article_id IS '기사 고유 ID';
COMMENT ON COLUMN article.press_id IS '언론사 ID';
COMMENT ON COLUMN article.news_date IS '뉴스 사이클 기준 날짜(KST 5:00 기준) - Python에서 계산하여 INSERT';
COMMENT ON COLUMN article.author IS '기사 작성자';
COMMENT ON COLUMN article.title IS '기사 제목';
COMMENT ON COLUMN article.content IS '기사 원문';
COMMENT ON COLUMN article.summary IS '기사 요약문';
COMMENT ON COLUMN article.article_url IS '원문 URL';
COMMENT ON COLUMN article.img_url IS '대표 이미지 URL';
COMMENT ON COLUMN article.published_at IS '기사 발행 일시';
COMMENT ON COLUMN article.created_at IS '데이터 수집 일시';
COMMENT ON COLUMN article.updated_at IS '데이터 최종 수정 일시 (자동 업데이트)';
COMMENT ON COLUMN article.embedding IS '768-dimensional embedding vector from ko-sroberta-multitask model';

-- 기사 테이블 인덱스
CREATE INDEX IF NOT EXISTS idx_published_at ON article(published_at);
CREATE INDEX IF NOT EXISTS idx_press_published ON article(press_id, published_at);
CREATE INDEX IF NOT EXISTS idx_news_date ON article(news_date DESC);
CREATE INDEX IF NOT EXISTS idx_article_embedding_cosine ON article USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
-- article_url은 UNIQUE 제약조건으로 자동 인덱스 생성되므로 별도 인덱스 불필요

-- ========================================
-- 3. 토픽 테이블 (topic)
-- ========================================
CREATE TABLE IF NOT EXISTS topic (
    topic_id BIGSERIAL PRIMARY KEY,
    topic_title VARCHAR(500) NOT NULL,
    main_article_id BIGINT NOT NULL,
    main_stance stance_type NOT NULL,
    main_stance_score DECIMAL(6, 5) NOT NULL,
    topic_date DATE NOT NULL,
    topic_rank SMALLINT NOT NULL,
    cluster_score DECIMAL(10, 5) NOT NULL,
    article_count INTEGER NOT NULL DEFAULT 0,
    centroid_embedding vector(768),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_updated TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

    -- 외래키
    CONSTRAINT fk_topic_main_article FOREIGN KEY (main_article_id) REFERENCES article(article_id),
    
    -- 제약조건
    CONSTRAINT chk_topic_rank CHECK (topic_rank BETWEEN 1 AND 10),
    CONSTRAINT chk_main_stance_score CHECK (main_stance_score BETWEEN -1 AND 1),
    CONSTRAINT uq_topic_date_rank UNIQUE (topic_date, topic_rank)
);

COMMENT ON TABLE topic IS '일일 주요 토픽을 저장하는 테이블 (Top 10)';
COMMENT ON COLUMN topic.topic_id IS '토픽 고유 ID';
COMMENT ON COLUMN topic.topic_title IS '토픽 제목';
COMMENT ON COLUMN topic.main_article_id IS '대표 기사의 ID';
COMMENT ON COLUMN topic.main_stance IS '대표 기사 스탠스';
COMMENT ON COLUMN topic.main_stance_score IS '대표 기사 스탠스 점수';
COMMENT ON COLUMN topic.topic_date IS '토픽 선정 날짜(1일 단위)';
COMMENT ON COLUMN topic.topic_rank IS '해당 날짜 토픽 순위 (1~10)';
COMMENT ON COLUMN topic.cluster_score IS '클러스터의 중요도 점수(기사 수, 최신성 등 반영)';
COMMENT ON COLUMN topic.article_count IS '해당 토픽에 속한 총 기사 개수';
COMMENT ON COLUMN topic.centroid_embedding IS '토픽의 중심 벡터 (incremental assignment 용)';
COMMENT ON COLUMN topic.is_active IS '토픽 활성화 상태';
COMMENT ON COLUMN topic.last_updated IS '토픽 최종 업데이트 일시';
COMMENT ON COLUMN topic.created_at IS '토픽 생성 일시';

-- 토픽 테이블 인덱스
CREATE INDEX IF NOT EXISTS idx_topic_date_rank ON topic(topic_date, topic_rank);
CREATE INDEX IF NOT EXISTS idx_cluster_score ON topic(topic_date, cluster_score DESC);

-- ========================================
-- 4. 토픽-기사 매핑 테이블 (topic_article_mapping)
-- ========================================
CREATE TABLE IF NOT EXISTS topic_article_mapping (
    topic_article_id BIGSERIAL PRIMARY KEY,
    topic_id BIGINT NOT NULL,
    article_id BIGINT NOT NULL,
    similarity_score DECIMAL(6, 5) NOT NULL,
    topic_date DATE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    
    -- 외래키
    CONSTRAINT fk_mapping_topic FOREIGN KEY (topic_id) REFERENCES topic(topic_id) ON DELETE CASCADE,
    CONSTRAINT fk_mapping_article FOREIGN KEY (article_id) REFERENCES article(article_id) ON DELETE CASCADE,
    
    -- 제약조건
    CONSTRAINT chk_similarity_score CHECK (similarity_score BETWEEN 0 AND 1),
    CONSTRAINT uq_topic_article UNIQUE (topic_id, article_id),
    CONSTRAINT uq_article_topic_date UNIQUE (article_id, topic_date)
);

COMMENT ON TABLE topic_article_mapping IS '토픽과 기사 간의 매핑 관계를 저장하는 테이블';
COMMENT ON COLUMN topic_article_mapping.topic_article_id IS '매핑 고유 ID';
COMMENT ON COLUMN topic_article_mapping.topic_id IS '토픽 ID';
COMMENT ON COLUMN topic_article_mapping.article_id IS '기사 ID';
COMMENT ON COLUMN topic_article_mapping.similarity_score IS '코사인 유사도 점수 (0~1)';
COMMENT ON COLUMN topic_article_mapping.topic_date IS '토픽 날짜';
COMMENT ON COLUMN topic_article_mapping.created_at IS '매핑 생성 일시';

-- 토픽-기사 매핑 인덱스
CREATE INDEX IF NOT EXISTS idx_similarity ON topic_article_mapping(topic_id, similarity_score DESC);
CREATE INDEX IF NOT EXISTS idx_article_date ON topic_article_mapping(article_id, topic_date);
CREATE INDEX IF NOT EXISTS idx_article_topic ON topic_article_mapping(article_id);

-- ========================================
-- 5. 스탠스 분석 테이블 (stance_analysis)
-- ========================================
CREATE TABLE IF NOT EXISTS stance_analysis (
    stance_id BIGSERIAL PRIMARY KEY,
    article_id BIGINT NOT NULL UNIQUE,
    stance_label stance_type NOT NULL,
    prob_positive DECIMAL(6, 5) NOT NULL,
    prob_neutral DECIMAL(6, 5) NOT NULL,
    prob_negative DECIMAL(6, 5) NOT NULL,
    stance_score DECIMAL(6, 5) NOT NULL,
    analyzed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    
    -- 외래키
    CONSTRAINT fk_stance_article FOREIGN KEY (article_id) REFERENCES article(article_id),
    
    -- 제약조건
    CONSTRAINT chk_prob_positive CHECK (prob_positive BETWEEN 0 AND 1),
    CONSTRAINT chk_prob_neutral CHECK (prob_neutral BETWEEN 0 AND 1),
    CONSTRAINT chk_prob_negative CHECK (prob_negative BETWEEN 0 AND 1),
    CONSTRAINT chk_stance_score CHECK (stance_score BETWEEN -1 AND 1),
    CONSTRAINT chk_prob_sum CHECK (ABS(prob_positive + prob_neutral + prob_negative - 1.0) <= 0.001),
    CONSTRAINT chk_stance_consistency CHECK (
        (stance_label = '옹호' AND prob_positive >= prob_neutral AND prob_positive >= prob_negative) OR
        (stance_label = '중립' AND prob_neutral >= prob_positive AND prob_neutral >= prob_negative) OR
        (stance_label = '비판' AND prob_negative >= prob_positive AND prob_negative >= prob_neutral)
    )
);

COMMENT ON TABLE stance_analysis IS '기사별 스탠스 분석 결과를 저장하는 테이블';
COMMENT ON COLUMN stance_analysis.stance_id IS '분석 결과 고유 ID';
COMMENT ON COLUMN stance_analysis.article_id IS '기사 ID (기사당 하나의 분석 결과만 존재)';
COMMENT ON COLUMN stance_analysis.stance_label IS '최종 분류 라벨 (옹호/중립/비판)';
COMMENT ON COLUMN stance_analysis.prob_positive IS '옹호 확률 (0~1)';
COMMENT ON COLUMN stance_analysis.prob_neutral IS '중립 확률 (0~1)';
COMMENT ON COLUMN stance_analysis.prob_negative IS '비판 확률 (0~1)';
COMMENT ON COLUMN stance_analysis.stance_score IS '스탠스 점수 = P(pos) - P(neg), 범위: [-1, 1]';
COMMENT ON COLUMN stance_analysis.analyzed_at IS '분석 수행 일시';

-- 스탠스 분석 인덱스
CREATE INDEX IF NOT EXISTS idx_stance_score ON stance_analysis(stance_label, stance_score);
CREATE INDEX IF NOT EXISTS idx_article_stance ON stance_analysis(article_id, stance_label);

-- ========================================
-- 6. 추천 기사 테이블 (recommended_article)
-- ========================================
CREATE TABLE IF NOT EXISTS recommended_article (
    recommended_id BIGSERIAL PRIMARY KEY,
    topic_id BIGINT NOT NULL,
    article_id BIGINT NOT NULL,
    press_id VARCHAR(10) NOT NULL,
    press_name VARCHAR(100) NOT NULL,
    title VARCHAR(300) NOT NULL,
    author VARCHAR(100),
    img_url VARCHAR(2083),
    article_url VARCHAR(2083) NOT NULL,
    recommendation_type stance_type NOT NULL,
    recommendation_rank SMALLINT NOT NULL,
    stance_score DECIMAL(6, 5) NOT NULL,
    published_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    
    -- 외래키
    CONSTRAINT fk_recommended_topic FOREIGN KEY (topic_id) REFERENCES topic(topic_id) ON DELETE CASCADE,
    CONSTRAINT fk_recommended_article FOREIGN KEY (article_id) REFERENCES article(article_id) ON DELETE CASCADE,
    CONSTRAINT fk_recommended_press FOREIGN KEY (press_id) REFERENCES press(press_id),
    
    -- 제약조건
    CONSTRAINT chk_recommendation_rank CHECK (recommendation_rank BETWEEN 1 AND 3),
    CONSTRAINT chk_recommended_stance_score CHECK (stance_score BETWEEN -1 AND 1),
    CONSTRAINT uq_topic_type_rank UNIQUE (topic_id, recommendation_type, recommendation_rank),
    CONSTRAINT uq_recommended_topic_article UNIQUE (topic_id, article_id)
);

COMMENT ON TABLE recommended_article IS '토픽별 추천 기사를 저장하는 테이블 (스탠스별 Top 3)';
COMMENT ON COLUMN recommended_article.recommended_id IS '추천 고유 ID';
COMMENT ON COLUMN recommended_article.topic_id IS '토픽 ID';
COMMENT ON COLUMN recommended_article.article_id IS '추천 기사 ID';
COMMENT ON COLUMN recommended_article.press_id IS '언론사 ID';
COMMENT ON COLUMN recommended_article.press_name IS '언론사 이름';
COMMENT ON COLUMN recommended_article.title IS '기사 제목';
COMMENT ON COLUMN recommended_article.author IS '기사 작성자';
COMMENT ON COLUMN recommended_article.img_url IS '대표 이미지 URL';
COMMENT ON COLUMN recommended_article.article_url IS '원문 URL';
COMMENT ON COLUMN recommended_article.recommendation_type IS '추천 유형 (옹호/중립/비판)';
COMMENT ON COLUMN recommended_article.recommendation_rank IS '해당 유형 내에서의 추천 순위 (1~3)';
COMMENT ON COLUMN recommended_article.stance_score IS '기사의 스탠스 점수 (-1~1)';
COMMENT ON COLUMN recommended_article.published_at IS '기사 발행 일시 (동점 시 최신 기사 우선)';
COMMENT ON COLUMN recommended_article.created_at IS '추천 생성 일시';

-- 추천 기사 인덱스
CREATE INDEX IF NOT EXISTS idx_topic_type_rank ON recommended_article(
    topic_id, 
    recommendation_type, 
    recommendation_rank
);

-- ========================================
-- 7. 대기 기사 테이블 (pending_articles)
-- ========================================
CREATE TABLE IF NOT EXISTS pending_articles (
    article_id BIGINT PRIMARY KEY,
    added_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    reason VARCHAR(50),
    max_similarity DECIMAL(5, 3),

    -- 외래키
    CONSTRAINT fk_pending_article FOREIGN KEY (article_id) REFERENCES article(article_id) ON DELETE CASCADE
);

COMMENT ON TABLE pending_articles IS '토픽 할당 대기 중인 기사 (유사도 임계값 미달)';
COMMENT ON COLUMN pending_articles.article_id IS '대기 중인 기사 ID';
COMMENT ON COLUMN pending_articles.added_at IS '대기 목록 추가 일시';
COMMENT ON COLUMN pending_articles.reason IS '대기 사유 (예: below_threshold)';
COMMENT ON COLUMN pending_articles.max_similarity IS '기존 토픽과의 최대 유사도';

-- 대기 기사 인덱스
CREATE INDEX IF NOT EXISTS idx_pending_articles_added_at ON pending_articles(added_at);

-- ========================================
-- 트리거: article.updated_at 자동 업데이트
-- ========================================
CREATE OR REPLACE FUNCTION update_article_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_update_article_updated_at ON article;
CREATE TRIGGER trg_update_article_updated_at
BEFORE UPDATE ON article
FOR EACH ROW
EXECUTE FUNCTION update_article_updated_at();

-- ========================================
-- 트리거: article_count 자동 업데이트
-- ========================================

-- INSERT 트리거 함수
CREATE OR REPLACE FUNCTION update_article_count_on_insert()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE topic 
    SET article_count = article_count + 1
    WHERE topic_id = NEW.topic_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- DELETE 트리거 함수
CREATE OR REPLACE FUNCTION update_article_count_on_delete()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE topic 
    SET article_count = article_count - 1
    WHERE topic_id = OLD.topic_id;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

-- INSERT 트리거
DROP TRIGGER IF EXISTS trg_update_article_count_insert ON topic_article_mapping;
CREATE TRIGGER trg_update_article_count_insert
AFTER INSERT ON topic_article_mapping
FOR EACH ROW
EXECUTE FUNCTION update_article_count_on_insert();

-- DELETE 트리거
DROP TRIGGER IF EXISTS trg_update_article_count_delete ON topic_article_mapping;
CREATE TRIGGER trg_update_article_count_delete
AFTER DELETE ON topic_article_mapping
FOR EACH ROW
EXECUTE FUNCTION update_article_count_on_delete();