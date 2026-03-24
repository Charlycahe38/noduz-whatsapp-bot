-- ============================================================
-- MIGRATION: Add clients table + client_id to existing tables
-- Run this in Supabase SQL Editor if you already have
-- conversations and appointments tables deployed.
-- ============================================================

-- 1. Create clients table
CREATE TABLE IF NOT EXISTS clients (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    business_name TEXT NOT NULL,
    business_type TEXT NOT NULL DEFAULT 'barbershop',
    business_location TEXT,
    business_address TEXT,
    whatsapp_phone_id TEXT UNIQUE NOT NULL,
    whatsapp_token TEXT NOT NULL,
    verify_token TEXT NOT NULL,
    app_secret TEXT,
    gemini_api_key TEXT,
    google_calendar_id TEXT DEFAULT 'primary',
    google_service_account_json TEXT,
    timezone TEXT DEFAULT 'America/Mexico_City',
    working_days TEXT DEFAULT 'Lunes a Domingo',
    business_start_hour INTEGER DEFAULT 9,
    business_end_hour INTEGER DEFAULT 20,
    break_start_hour INTEGER,
    break_end_hour INTEGER,
    slot_increment INTEGER DEFAULT 30,
    services JSONB DEFAULT '[]'::jsonb,
    barbers JSONB DEFAULT '[]'::jsonb,
    bot_language TEXT DEFAULT 'Spanish',
    bot_greeting TEXT,
    cancellation_policy TEXT,
    post_confirmation_message TEXT,
    deposit_required BOOLEAN DEFAULT FALSE,
    extra_instructions TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE clients ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access" ON clients FOR ALL USING (true);
CREATE INDEX IF NOT EXISTS idx_clients_phone_id ON clients(whatsapp_phone_id);

-- 2. Insert your existing client (Family Barber) so existing rows can reference it
-- UPDATE the values below with your actual credentials before running
INSERT INTO clients (
    business_name,
    business_type,
    business_location,
    whatsapp_phone_id,
    whatsapp_token,
    verify_token,
    app_secret,
    gemini_api_key,
    google_calendar_id,
    timezone,
    working_days,
    business_start_hour,
    business_end_hour,
    break_start_hour,
    break_end_hour,
    slot_increment,
    services,
    barbers,
    bot_language,
    bot_greeting,
    cancellation_policy,
    post_confirmation_message,
    deposit_required
) VALUES (
    'Family Barber',
    'barbershop',
    'San Luis Potosí, México',
    'YOUR_WHATSAPP_PHONE_ID',       -- replace
    'YOUR_WHATSAPP_TOKEN',          -- replace
    'Noduz2026',
    'YOUR_APP_SECRET',              -- replace
    'YOUR_GEMINI_API_KEY',          -- replace
    'primary',
    'America/Mexico_City',
    'Lunes a Domingo',
    11,
    20,
    14,
    16,
    30,
    '[
        {"name": "Corte de cabello", "duration": 45, "price": 200},
        {"name": "Corte y barba",    "duration": 80, "price": 300},
        {"name": "Barba",            "duration": 45, "price": 150}
    ]'::jsonb,
    '["Daniel", "Enrique", "Juan", "Pedro"]'::jsonb,
    'Spanish',
    'Que onda! En que te puedo ayudar?',
    'Si necesitas cancelar, avísanos con al menos 1 hora de anticipación.',
    'No se te olvide llegar 5 minutos antes!',
    false
);

-- 3. Add client_id column to conversations (nullable first, then we backfill)
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS client_id UUID REFERENCES clients(id) ON DELETE CASCADE;

-- 4. Backfill: link all existing conversations to Family Barber
UPDATE conversations
SET client_id = (SELECT id FROM clients WHERE business_name = 'Family Barber' LIMIT 1)
WHERE client_id IS NULL;

-- 5. Add client_id column to appointments
ALTER TABLE appointments ADD COLUMN IF NOT EXISTS client_id UUID REFERENCES clients(id) ON DELETE CASCADE;

-- 6. Backfill appointments
UPDATE appointments
SET client_id = (SELECT id FROM clients WHERE business_name = 'Family Barber' LIMIT 1)
WHERE client_id IS NULL;

-- 7. Drop old UNIQUE(customer_phone) and replace with UNIQUE(client_id, customer_phone)
-- (Only do this after backfilling — skips if constraint doesn't exist)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'conversations_customer_phone_key'
    ) THEN
        ALTER TABLE conversations DROP CONSTRAINT conversations_customer_phone_key;
    END IF;
END $$;

ALTER TABLE conversations DROP CONSTRAINT IF EXISTS conversations_client_id_customer_phone_key;
ALTER TABLE conversations ADD CONSTRAINT conversations_client_id_customer_phone_key UNIQUE (client_id, customer_phone);

-- 8. Add indexes
CREATE INDEX IF NOT EXISTS idx_conversations_client ON conversations(client_id);
CREATE INDEX IF NOT EXISTS idx_appointments_client ON appointments(client_id);

-- Done!
-- Each new client gets a row in the clients table.
-- conversations and appointments are now scoped per client.
