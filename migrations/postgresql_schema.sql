-- ============================================================================
-- PostgreSQL Schema for Financial Agent
-- Migration from SQLite to PostgreSQL with optimizations
-- ============================================================================

-- Enable UUID extension for better primary keys
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable pg_trgm for better text search performance
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================================
-- USERS SCHEMA
-- ============================================================================

-- Users table with robust constraints and indexes
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT users_username_min_length CHECK (LENGTH(username) >= 3),
    CONSTRAINT users_email_format CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'),
    CONSTRAINT users_username_unique UNIQUE (username),
    CONSTRAINT users_email_unique UNIQUE (email)
);

-- Indexes for users table
CREATE INDEX IF NOT EXISTS idx_users_username ON users USING btree (username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users USING btree (email);
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users (is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_users_created_at ON users USING btree (created_at DESC);

-- Trigger to auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Comment on table
COMMENT ON TABLE users IS 'Store user accounts with authentication information';
COMMENT ON COLUMN users.hashed_password IS 'Bcrypt hashed password';

-- ============================================================================
-- REFRESH TOKENS SCHEMA
-- ============================================================================

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    token VARCHAR(500) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Foreign key with cascade delete
    CONSTRAINT fk_refresh_tokens_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    -- Unique constraint on token
    CONSTRAINT refresh_tokens_token_unique UNIQUE (token),

    -- Check expiration is in the future when created
    CONSTRAINT refresh_tokens_expires_future CHECK (expires_at > created_at)
);

-- Indexes for refresh_tokens
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens USING btree (user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_refresh_tokens_token ON refresh_tokens USING btree (token);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires_at ON refresh_tokens USING btree (expires_at);

-- Composite index for user_id and expires_at (for queries filtering both)
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_expires
    ON refresh_tokens (user_id, expires_at);

COMMENT ON TABLE refresh_tokens IS 'Store refresh tokens for JWT authentication';

-- ============================================================================
-- CONVERSATIONS SCHEMA
-- ============================================================================

CREATE TABLE IF NOT EXISTS conversations (
    session_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id BIGINT,
    title VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Foreign key to users (optional - can be anonymous)
    CONSTRAINT fk_conversations_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE SET NULL
        ON UPDATE CASCADE
);

-- Indexes for conversations
CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations USING btree (user_id) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON conversations USING btree (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_updated_at ON conversations USING btree (updated_at DESC);

-- Composite index for user sessions sorted by date
CREATE INDEX IF NOT EXISTS idx_conversations_user_updated
    ON conversations (user_id, updated_at DESC)
    WHERE user_id IS NOT NULL;

-- Trigger to auto-update updated_at
CREATE TRIGGER conversations_updated_at
    BEFORE UPDATE ON conversations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

COMMENT ON TABLE conversations IS 'Store chat sessions/conversations';
COMMENT ON COLUMN conversations.user_id IS 'User ID - NULL for anonymous sessions';

-- ============================================================================
-- MESSAGES SCHEMA
-- ============================================================================

CREATE TYPE message_role AS ENUM ('user', 'assistant');

CREATE TABLE IF NOT EXISTS messages (
    id BIGSERIAL PRIMARY KEY,
    session_id UUID NOT NULL,
    role message_role NOT NULL,
    content TEXT,
    answer TEXT,
    sources_json JSONB,
    model_used VARCHAR(100),
    confidence NUMERIC(3, 2),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Foreign key with cascade delete
    CONSTRAINT fk_messages_session
        FOREIGN KEY (session_id)
        REFERENCES conversations(session_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    -- Constraints
    CONSTRAINT messages_confidence_range CHECK (confidence >= 0 AND confidence <= 1),
    CONSTRAINT messages_has_content CHECK (
        (role = 'user' AND content IS NOT NULL) OR
        (role = 'assistant' AND answer IS NOT NULL)
    )
);

-- Indexes for messages
CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages USING btree (session_id);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages USING btree (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_messages_session_timestamp ON messages (session_id, timestamp ASC);

-- Index for full-text search on content and answer
CREATE INDEX IF NOT EXISTS idx_messages_content_trgm
    ON messages USING gin (content gin_trgm_ops) WHERE content IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_messages_answer_trgm
    ON messages USING gin (answer gin_trgm_ops) WHERE answer IS NOT NULL;

-- JSONB index for sources
CREATE INDEX IF NOT EXISTS idx_messages_sources_jsonb
    ON messages USING gin (sources_json) WHERE sources_json IS NOT NULL;

-- Partial index for user messages
CREATE INDEX IF NOT EXISTS idx_messages_user
    ON messages (session_id, timestamp) WHERE role = 'user';

-- Partial index for assistant messages with confidence
CREATE INDEX IF NOT EXISTS idx_messages_assistant_confidence
    ON messages (confidence DESC) WHERE role = 'assistant' AND confidence IS NOT NULL;

-- Trigger to update conversation updated_at when message is added
CREATE OR REPLACE FUNCTION update_conversation_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE conversations
    SET updated_at = NEW.timestamp
    WHERE session_id = NEW.session_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER messages_update_conversation
    AFTER INSERT ON messages
    FOR EACH ROW
    EXECUTE FUNCTION update_conversation_timestamp();

COMMENT ON TABLE messages IS 'Store chat messages within conversations';
COMMENT ON COLUMN messages.sources_json IS 'JSON array of source documents used for RAG';
COMMENT ON COLUMN messages.confidence IS 'Confidence score from 0 to 1';

-- ============================================================================
-- FEEDBACK SCHEMA
-- ============================================================================

CREATE TYPE feedback_rating AS ENUM ('positive', 'negative', 'neutral');

CREATE TABLE IF NOT EXISTS feedback (
    id BIGSERIAL PRIMARY KEY,
    session_id UUID NOT NULL,
    message_id BIGINT NOT NULL,
    rating feedback_rating NOT NULL,
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Foreign keys with cascade delete
    CONSTRAINT fk_feedback_session
        FOREIGN KEY (session_id)
        REFERENCES conversations(session_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_feedback_message
        FOREIGN KEY (message_id)
        REFERENCES messages(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    -- Prevent duplicate feedback for same message
    CONSTRAINT feedback_message_unique UNIQUE (message_id)
);

-- Indexes for feedback
CREATE INDEX IF NOT EXISTS idx_feedback_session_id ON feedback USING btree (session_id);
CREATE INDEX IF NOT EXISTS idx_feedback_message_id ON feedback USING btree (message_id);
CREATE INDEX IF NOT EXISTS idx_feedback_rating ON feedback USING btree (rating);
CREATE INDEX IF NOT EXISTS idx_feedback_created_at ON feedback USING btree (created_at DESC);

-- Index for text search on comments
CREATE INDEX IF NOT EXISTS idx_feedback_comment_trgm
    ON feedback USING gin (comment gin_trgm_ops) WHERE comment IS NOT NULL;

COMMENT ON TABLE feedback IS 'Store user feedback on assistant responses';

-- ============================================================================
-- MATERIALIZED VIEW FOR ANALYTICS
-- ============================================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS conversation_statistics AS
SELECT
    c.session_id,
    c.user_id,
    c.created_at,
    COUNT(m.id) AS total_messages,
    COUNT(CASE WHEN m.role = 'user' THEN 1 END) AS user_messages,
    COUNT(CASE WHEN m.role = 'assistant' THEN 1 END) AS assistant_messages,
    AVG(CASE WHEN m.role = 'assistant' THEN m.confidence END) AS avg_confidence,
    COUNT(f.id) AS feedback_count,
    COUNT(CASE WHEN f.rating = 'positive' THEN 1 END) AS positive_feedback,
    COUNT(CASE WHEN f.rating = 'negative' THEN 1 END) AS negative_feedback,
    MAX(m.timestamp) AS last_message_at
FROM conversations c
LEFT JOIN messages m ON c.session_id = m.session_id
LEFT JOIN feedback f ON m.id = f.message_id
GROUP BY c.session_id, c.user_id, c.created_at;

-- Index on materialized view
CREATE INDEX IF NOT EXISTS idx_conv_stats_user_id
    ON conversation_statistics (user_id) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_conv_stats_created_at
    ON conversation_statistics (created_at DESC);

COMMENT ON MATERIALIZED VIEW conversation_statistics
    IS 'Pre-computed conversation statistics for analytics dashboard';

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Function to clean expired refresh tokens
CREATE OR REPLACE FUNCTION cleanup_expired_tokens()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM refresh_tokens
    WHERE expires_at < NOW();

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION cleanup_expired_tokens()
    IS 'Delete expired refresh tokens and return count';

-- Function to purge old conversations
CREATE OR REPLACE FUNCTION purge_old_conversations(retention_days INTEGER DEFAULT 90)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM conversations
    WHERE created_at < NOW() - (retention_days || ' days')::INTERVAL;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION purge_old_conversations(INTEGER)
    IS 'Delete conversations older than specified days (default 90)';

-- Function to refresh materialized view
CREATE OR REPLACE FUNCTION refresh_conversation_stats()
RETURNS VOID AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY conversation_statistics;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION refresh_conversation_stats()
    IS 'Refresh conversation statistics materialized view';

-- ============================================================================
-- PERMISSIONS (adjust based on your security requirements)
-- ============================================================================

-- Create application user (run separately with appropriate credentials)
-- CREATE USER financial_agent_app WITH PASSWORD 'your_secure_password';
-- GRANT CONNECT ON DATABASE your_database TO financial_agent_app;
-- GRANT USAGE ON SCHEMA public TO financial_agent_app;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO financial_agent_app;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO financial_agent_app;
-- GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO financial_agent_app;

-- ============================================================================
-- COMPLETION MESSAGE
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '✅ PostgreSQL schema created successfully!';
    RAISE NOTICE 'Tables: users, refresh_tokens, conversations, messages, feedback';
    RAISE NOTICE 'Materialized View: conversation_statistics';
    RAISE NOTICE 'Helper Functions: cleanup_expired_tokens, purge_old_conversations, refresh_conversation_stats';
END $$;
