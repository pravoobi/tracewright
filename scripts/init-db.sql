-- Runs once on first postgres container startup
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- fuzzy text matching for logical_id reconciliation

-- Langfuse gets its own DB
CREATE DATABASE langfuse;
