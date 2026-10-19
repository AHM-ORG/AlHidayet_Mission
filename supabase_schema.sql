-- ============================================================================
-- SUPABASE PRODUCTION DATABASE SCHEMA & STORAGE POLICIES FOR AHM-WEB
-- ============================================================================
-- Run this complete script in your Supabase SQL Editor:
-- Dashboard -> SQL Editor -> New Query -> Paste & Run
-- ============================================================================

-- 1. Create or ensure the Supabase Storage Bucket 'documents' exists & is public
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'documents', 
    'documents', 
    true, 
    52428800, -- 50 MB max ceiling (Compression firewall handles <= 2MB target)
    ARRAY[
        'image/jpeg', 'image/png', 'image/webp', 'image/gif',
        'application/pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        'text/plain', 'text/csv'
    ]
)
ON CONFLICT (id) DO UPDATE 
SET public = true;

-- 2. Storage Bucket Row-Level Security (RLS) Policies
-- Allow anyone to publicly view/download files stored in the 'documents' bucket
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'objects' 
        AND schemaname = 'storage' 
        AND policyname = 'Public Access for documents bucket'
    ) THEN
        CREATE POLICY "Public Access for documents bucket" 
        ON storage.objects FOR SELECT 
        USING (bucket_id = 'documents');
    END IF;
END $$;

-- Allow Service Role key full access (automatic, but explicit for clarity)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'objects' 
        AND schemaname = 'storage' 
        AND policyname = 'Service Role full access on documents'
    ) THEN
        CREATE POLICY "Service Role full access on documents" 
        ON storage.objects FOR ALL 
        TO service_role 
        USING (bucket_id = 'documents')
        WITH CHECK (bucket_id = 'documents');
    END IF;
END $$;

-- 3. Create user_posts Table for User Submissions & Content Moderation
CREATE TABLE IF NOT EXISTS public.user_posts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'anonymous',
    file_name TEXT NOT NULL,
    file_url TEXT NOT NULL,
    storage_path TEXT,
    mime_type TEXT,
    file_size BIGINT,
    status TEXT NOT NULL DEFAULT 'pending_review' 
        CHECK (status IN ('pending_review', 'published', 'rejected')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- Indexes for lightning-fast queries
CREATE INDEX IF NOT EXISTS idx_user_posts_status ON public.user_posts(status);
CREATE INDEX IF NOT EXISTS idx_user_posts_user_id ON public.user_posts(user_id);
CREATE INDEX IF NOT EXISTS idx_user_posts_created_at ON public.user_posts(created_at DESC);

-- 4. Enable RLS on user_posts
ALTER TABLE public.user_posts ENABLE ROW LEVEL SECURITY;

-- Public can ONLY view documents that are officially 'published'
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'user_posts' 
        AND schemaname = 'public' 
        AND policyname = 'Public View Published Posts'
    ) THEN
        CREATE POLICY "Public View Published Posts" 
        ON public.user_posts FOR SELECT 
        TO anon, authenticated
        USING (status = 'published');
    END IF;
END $$;

-- Service Role key has full administrative control (Review, Approve, Reject, Delete)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'user_posts' 
        AND schemaname = 'public' 
        AND policyname = 'Service Role full access on user_posts'
    ) THEN
        CREATE POLICY "Service Role full access on user_posts" 
        ON public.user_posts FOR ALL 
        TO service_role 
        USING (true)
        WITH CHECK (true);
    END IF;
END $$;

-- 5. Create storage_mappings Table for Mirroring School Files
CREATE TABLE IF NOT EXISTS public.storage_mappings (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    filename TEXT NOT NULL UNIQUE,
    storage_path TEXT NOT NULL,
    public_url TEXT NOT NULL,
    mime_type TEXT,
    file_size BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_storage_mappings_filename ON public.storage_mappings(filename);
CREATE INDEX IF NOT EXISTS idx_storage_mappings_storage_path ON public.storage_mappings(storage_path);

-- Enable RLS on storage_mappings
ALTER TABLE public.storage_mappings ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'storage_mappings' 
        AND schemaname = 'public' 
        AND policyname = 'Public View Storage Mappings'
    ) THEN
        CREATE POLICY "Public View Storage Mappings" 
        ON public.storage_mappings FOR SELECT 
        TO anon, authenticated
        USING (true);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'storage_mappings' 
        AND schemaname = 'public' 
        AND policyname = 'Service Role full access on storage_mappings'
    ) THEN
        CREATE POLICY "Service Role full access on storage_mappings" 
        ON public.storage_mappings FOR ALL 
        TO service_role 
        USING (true)
        WITH CHECK (true);
    END IF;
END $$;
