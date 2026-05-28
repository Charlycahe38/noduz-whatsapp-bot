-- Migration: add per-customer processing lock + message queue
-- Run this in Supabase SQL Editor BEFORE deploying the updated code.

-- 1. Add lock columns to the existing conversations table
ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS processing_lock    BOOLEAN    DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS lock_acquired_at   TIMESTAMPTZ;

-- 2. Message queue table: stores every incoming message before processing
CREATE TABLE IF NOT EXISTS message_queue (
    id              UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    client_id       TEXT        NOT NULL,
    customer_phone  TEXT        NOT NULL,
    customer_name   TEXT        DEFAULT 'Cliente',
    message_body    TEXT        NOT NULL,
    received_at     TIMESTAMPTZ DEFAULT NOW(),
    processed       BOOLEAN     DEFAULT FALSE
);

-- Index for the hot query: "give me all pending messages for this customer, oldest first"
CREATE INDEX IF NOT EXISTS idx_message_queue_pending
    ON message_queue (client_id, customer_phone, processed, received_at);

-- RLS (same open policy as the other tables — service role handles auth)
ALTER TABLE message_queue ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'message_queue' AND policyname = 'Service role full access'
    ) THEN
        CREATE POLICY "Service role full access" ON message_queue FOR ALL USING (true);
    END IF;
END$$;

-- Optional: auto-clean processed messages older than 7 days to keep the table lean
-- (run manually or set up a Supabase scheduled function if needed)
-- DELETE FROM message_queue WHERE processed = TRUE AND received_at < NOW() - INTERVAL '7 days';
