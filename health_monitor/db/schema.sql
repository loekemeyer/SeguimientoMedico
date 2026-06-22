-- Esquema PostgreSQL de la Historia Clínica Electrónica (HCE).
-- Campos sensibles (PII / clínicos) se almacenan cifrados con AES-256 (sufijo _enc).
-- Cargado automáticamente por docker-compose en el primer arranque.

CREATE TABLE IF NOT EXISTS pacientes (
    id                          SERIAL PRIMARY KEY,
    hce_id                      VARCHAR(64) UNIQUE NOT NULL,
    nombre_enc                  TEXT NOT NULL,
    telefono_whatsapp_enc       TEXT NOT NULL,
    familiares_enc              JSONB NOT NULL DEFAULT '[]',
    consentimiento_firmado      BOOLEAN NOT NULL DEFAULT FALSE,
    consentimiento_fecha        TIMESTAMPTZ,
    consentimiento_apoderado_enc TEXT,
    activo                      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pacientes_hce ON pacientes (hce_id);

CREATE TABLE IF NOT EXISTS ficha_clinica (
    id              SERIAL PRIMARY KEY,
    paciente_id     INTEGER NOT NULL UNIQUE REFERENCES pacientes (id) ON DELETE CASCADE,
    limites         JSONB NOT NULL DEFAULT '{}',   -- rangos personalizados de control
    medicacion_enc  JSONB NOT NULL DEFAULT '[]',   -- [{droga, dosis, frecuencia}] cifrado
    patologias      JSONB NOT NULL DEFAULT '[]',   -- códigos CIE-10
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS evolucion_diaria (
    id                  SERIAL PRIMARY KEY,
    paciente_id         INTEGER NOT NULL REFERENCES pacientes (id) ON DELETE CASCADE,
    fecha               TIMESTAMPTZ NOT NULL DEFAULT now(),
    readout             JSONB NOT NULL DEFAULT '{}',  -- ClinicalReadout serializado
    nivel_alerta        VARCHAR(16) NOT NULL DEFAULT 'VERDE',
    motivos             JSONB NOT NULL DEFAULT '[]',
    transcripcion_enc   TEXT                          -- transcripción completa (cifrada)
);

CREATE INDEX IF NOT EXISTS idx_evolucion_paciente ON evolucion_diaria (paciente_id, fecha DESC);
