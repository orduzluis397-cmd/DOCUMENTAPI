-- Extensiones requeridas por Contable IA. Se ejecuta solo al crear el volumen por primera vez.
-- vector: embeddings para RAG (pgvector). unaccent: búsqueda de texto en español sin tildes.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- Plantilla: que las bases creadas después también las tengan (p. ej. la de pruebas).
\connect template1
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS unaccent;
