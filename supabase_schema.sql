-- SonicRead Database Schema for Supabase
-- Run this SQL in your Supabase SQL editor to set up the database

-- Enable UUID extension for generating IDs
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Users table for authentication
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- User PDFs table (metadata only - files stored locally)
CREATE TABLE IF NOT EXISTS user_pdfs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    file_id VARCHAR(255) UNIQUE NOT NULL, -- UUID for the local file
    local_filename VARCHAR(255) NOT NULL, -- actual filename in local storage
    file_size INTEGER, -- file size in bytes
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Reading progress tracking
CREATE TABLE IF NOT EXISTS reading_progress (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    pdf_id VARCHAR(255) REFERENCES user_pdfs(file_id) ON DELETE CASCADE,
    current_page INTEGER DEFAULT 1,
    current_word_index INTEGER DEFAULT 0,
    total_words INTEGER DEFAULT 0,
    progress_percentage DECIMAL(5,2) GENERATED ALWAYS AS (
        CASE 
            WHEN total_words > 0 THEN (current_word_index::DECIMAL / total_words::DECIMAL) * 100
            ELSE 0
        END
    ) STORED,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, pdf_id)
);

-- Indexes for better performance
CREATE INDEX IF NOT EXISTS idx_user_pdfs_user_id ON user_pdfs(user_id);
CREATE INDEX IF NOT EXISTS idx_user_pdfs_file_id ON user_pdfs(file_id);
CREATE INDEX IF NOT EXISTS idx_reading_progress_user_id ON reading_progress(user_id);
CREATE INDEX IF NOT EXISTS idx_reading_progress_pdf_id ON reading_progress(pdf_id);
CREATE INDEX IF NOT EXISTS idx_reading_progress_updated_at ON reading_progress(updated_at DESC);

-- Row Level Security (RLS) policies
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_pdfs ENABLE ROW LEVEL SECURITY;
ALTER TABLE reading_progress ENABLE ROW LEVEL SECURITY;

-- Users can only access their own data
CREATE POLICY "Users can view own profile" ON users
    FOR SELECT USING (auth.uid() = id);

CREATE POLICY "Users can update own profile" ON users
    FOR UPDATE USING (auth.uid() = id);

-- Users can only access their own PDFs
CREATE POLICY "Users can view own PDFs" ON user_pdfs
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own PDFs" ON user_pdfs
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own PDFs" ON user_pdfs
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own PDFs" ON user_pdfs
    FOR DELETE USING (auth.uid() = user_id);

-- Users can only access their own reading progress
CREATE POLICY "Users can view own reading progress" ON reading_progress
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own reading progress" ON reading_progress
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own reading progress" ON reading_progress
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own reading progress" ON reading_progress
    FOR DELETE USING (auth.uid() = user_id);

-- Function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers to automatically update updated_at
CREATE TRIGGER update_users_updated_at 
    BEFORE UPDATE ON users 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_user_pdfs_updated_at 
    BEFORE UPDATE ON user_pdfs 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_reading_progress_updated_at 
    BEFORE UPDATE ON reading_progress 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function to clean up orphaned reading progress
CREATE OR REPLACE FUNCTION cleanup_orphaned_reading_progress()
RETURNS void AS $$
BEGIN
    DELETE FROM reading_progress 
    WHERE pdf_id NOT IN (SELECT file_id FROM user_pdfs);
END;
$$ LANGUAGE plpgsql;

-- Function to get user's PDFs with reading progress
CREATE OR REPLACE FUNCTION get_user_pdfs_with_progress(user_uuid UUID)
RETURNS TABLE(
    id UUID,
    filename VARCHAR,
    file_id VARCHAR,
    file_size INTEGER,
    created_at TIMESTAMP WITH TIME ZONE,
    current_page INTEGER,
    current_word_index INTEGER,
    total_words INTEGER,
    progress_percentage DECIMAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        p.id,
        p.filename,
        p.file_id,
        p.file_size,
        p.created_at,
        COALESCE(rp.current_page, 1) as current_page,
        COALESCE(rp.current_word_index, 0) as current_word_index,
        COALESCE(rp.total_words, 0) as total_words,
        COALESCE(rp.progress_percentage, 0.0) as progress_percentage
    FROM user_pdfs p
    LEFT JOIN reading_progress rp ON p.file_id = rp.pdf_id
    WHERE p.user_id = user_uuid
    ORDER BY p.created_at DESC;
END;
$$ LANGUAGE plpgsql;

-- Function to get user statistics
CREATE OR REPLACE FUNCTION get_user_stats(user_uuid UUID)
RETURNS JSON AS $$
DECLARE
    result JSON;
BEGIN
    SELECT json_build_object(
        'total_pdfs', COUNT(DISTINCT p.id),
        'total_reading_time', COALESCE(SUM(rp.current_word_index), 0),
        'pdfs_completed', COUNT(DISTINCT CASE WHEN rp.progress_percentage >= 100 THEN p.id END)
    ) INTO result
    FROM user_pdfs p
    LEFT JOIN reading_progress rp ON p.file_id = rp.pdf_id
    WHERE p.user_id = user_uuid;
    
    RETURN result;
END;
$$ LANGUAGE plpgsql;

-- Comments for documentation
COMMENT ON TABLE users IS 'User profiles extending Supabase auth.users';
COMMENT ON TABLE user_pdfs IS 'PDF file metadata - actual files stored locally';
COMMENT ON TABLE reading_progress IS 'Reading progress tracking for each user-PDF combination';

COMMENT ON COLUMN reading_progress.progress_percentage IS 'Automatically calculated progress percentage based on current_word_index and total_words';
COMMENT ON COLUMN user_pdfs.file_id IS 'UUID identifier for the local file';
COMMENT ON COLUMN user_pdfs.local_filename IS 'Actual filename in local storage system';
COMMENT ON COLUMN reading_progress.current_word_index IS 'Index of the current word being read (0-based)';
COMMENT ON COLUMN reading_progress.current_page IS 'Current page number (1-based)'; 