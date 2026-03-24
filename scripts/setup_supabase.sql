-- ============================================================
-- Noduz WhatsApp Bot — Multi-Client Schema
-- Run this in Supabase SQL Editor
-- ============================================================

-- Clients table: one row per business using the bot
CREATE TABLE IF NOT EXISTS clients (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    -- Identity
    business_name TEXT NOT NULL,
    business_type TEXT NOT NULL DEFAULT 'barbershop',
    business_location TEXT,
    business_address TEXT,
    -- WhatsApp credentials (per client)
    whatsapp_phone_id TEXT UNIQUE NOT NULL,
    whatsapp_token TEXT NOT NULL,
    verify_token TEXT NOT NULL,
    app_secret TEXT,
    -- AI
    gemini_api_key TEXT,
    -- Google Calendar
    google_calendar_id TEXT DEFAULT 'primary',
    google_service_account_json TEXT,
    -- Business hours
    timezone TEXT DEFAULT 'America/Mexico_City',
    working_days TEXT DEFAULT 'Lunes a Domingo',
    business_start_hour INTEGER DEFAULT 9,
    business_end_hour INTEGER DEFAULT 20,
    break_start_hour INTEGER,
    break_end_hour INTEGER,
    slot_increment INTEGER DEFAULT 30,
    -- Services catalog: [{"name": "Corte", "duration": 45, "price": 200}, ...]
    services JSONB DEFAULT '[]'::jsonb,
    -- Staff / barbers: ["Daniel", "Enrique"] or [] if single operator
    barbers JSONB DEFAULT '[]'::jsonb,
    -- Bot personality
    bot_language TEXT DEFAULT 'Spanish',
    bot_greeting TEXT,
    cancellation_policy TEXT,
    post_confirmation_message TEXT,
    deposit_required BOOLEAN DEFAULT FALSE,
    extra_instructions TEXT,
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Conversations table: tracks chat state per customer per client
CREATE TABLE IF NOT EXISTS conversations (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    customer_phone TEXT NOT NULL,
    customer_name TEXT DEFAULT 'Cliente',
    messages JSONB DEFAULT '[]'::jsonb,
    last_message_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(client_id, customer_phone)
);

-- Appointments table: all confirmed bookings per client
CREATE TABLE IF NOT EXISTS appointments (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    customer_name TEXT NOT NULL,
    customer_phone TEXT NOT NULL,
    service TEXT NOT NULL,
    appointment_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    duration_minutes INTEGER NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    currency TEXT DEFAULT 'MXN',
    google_event_id TEXT,
    status TEXT DEFAULT 'confirmed',
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Row Level Security
ALTER TABLE clients ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE appointments ENABLE ROW LEVEL SECURITY;

-- Allow service role full access
CREATE POLICY "Service role full access" ON clients FOR ALL USING (true);
CREATE POLICY "Service role full access" ON conversations FOR ALL USING (true);
CREATE POLICY "Service role full access" ON appointments FOR ALL USING (true);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_clients_phone_id ON clients(whatsapp_phone_id);
CREATE INDEX IF NOT EXISTS idx_conversations_client ON conversations(client_id);
CREATE INDEX IF NOT EXISTS idx_conversations_phone ON conversations(customer_phone);
CREATE INDEX IF NOT EXISTS idx_appointments_client ON appointments(client_id);
CREATE INDEX IF NOT EXISTS idx_appointments_date ON appointments(appointment_date);
CREATE INDEX IF NOT EXISTS idx_appointments_phone ON appointments(customer_phone);
