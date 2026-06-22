-- Esquema PostgreSQL de la HCE — versión SaaS multi-usuario.
-- Campos sensibles (PII / clínicos) se almacenan cifrados con AES-256 (sufijo _enc).
-- Cargado automáticamente por docker-compose en el primer arranque.

CREATE TABLE IF NOT EXISTS usuarios (
    id                  SERIAL PRIMARY KEY,
    email               VARCHAR(255) UNIQUE NOT NULL,
    password_hash       TEXT NOT NULL,
    nombre              VARCHAR(120) NOT NULL DEFAULT '',
    plan                VARCHAR(32) NOT NULL DEFAULT 'trial',
    suscripcion_vence   TIMESTAMPTZ,
    activo              BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pacientes (
    id                          SERIAL PRIMARY KEY,
    usuario_id                  INTEGER NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    hce_id                      VARCHAR(64) UNIQUE NOT NULL,
    nombre_enc                  TEXT NOT NULL,
    telefono_whatsapp_enc       TEXT NOT NULL,
    consentimiento_firmado      BOOLEAN NOT NULL DEFAULT FALSE,
    consentimiento_fecha        TIMESTAMPTZ,
    consentimiento_apoderado_enc TEXT,
    activo                      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_pacientes_usuario ON pacientes (usuario_id);

CREATE TABLE IF NOT EXISTS ficha_clinica (
    id              SERIAL PRIMARY KEY,
    paciente_id     INTEGER NOT NULL UNIQUE REFERENCES pacientes (id) ON DELETE CASCADE,
    limites         JSONB NOT NULL DEFAULT '{}',
    patologias      JSONB NOT NULL DEFAULT '[]',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS medicacion (
    id              SERIAL PRIMARY KEY,
    paciente_id     INTEGER NOT NULL REFERENCES pacientes (id) ON DELETE CASCADE,
    nombre_enc      TEXT NOT NULL,
    frecuencia      VARCHAR(120) NOT NULL DEFAULT '',
    activa          BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS idx_medicacion_paciente ON medicacion (paciente_id);

CREATE TABLE IF NOT EXISTS contactos_emergencia (
    id              SERIAL PRIMARY KEY,
    paciente_id     INTEGER NOT NULL REFERENCES pacientes (id) ON DELETE CASCADE,
    nombre_enc      TEXT NOT NULL,
    telefono_enc    TEXT NOT NULL,
    relacion        VARCHAR(60) NOT NULL DEFAULT '',
    prioridad       INTEGER NOT NULL DEFAULT 1,
    recibe_alertas  BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS idx_contactos_paciente ON contactos_emergencia (paciente_id, prioridad);

CREATE TABLE IF NOT EXISTS evolucion_diaria (
    id                  SERIAL PRIMARY KEY,
    paciente_id         INTEGER NOT NULL REFERENCES pacientes (id) ON DELETE CASCADE,
    fecha               TIMESTAMPTZ NOT NULL DEFAULT now(),
    readout             JSONB NOT NULL DEFAULT '{}',
    nivel_alerta        VARCHAR(16) NOT NULL DEFAULT 'VERDE',
    motivos             JSONB NOT NULL DEFAULT '[]',
    resumen             TEXT NOT NULL DEFAULT '',
    transcripcion_enc   TEXT
);
CREATE INDEX IF NOT EXISTS idx_evolucion_paciente ON evolucion_diaria (paciente_id, fecha DESC);

CREATE TABLE IF NOT EXISTS notificaciones (
    id              SERIAL PRIMARY KEY,
    paciente_id     INTEGER NOT NULL REFERENCES pacientes (id) ON DELETE CASCADE,
    evolucion_id    INTEGER REFERENCES evolucion_diaria (id) ON DELETE CASCADE,
    fecha           TIMESTAMPTZ NOT NULL DEFAULT now(),
    canal           VARCHAR(20) NOT NULL,
    nivel_alerta    VARCHAR(16) NOT NULL DEFAULT 'VERDE',
    destino_enc     TEXT NOT NULL,
    destino_label   VARCHAR(120) NOT NULL DEFAULT '',
    contenido       TEXT NOT NULL DEFAULT '',
    enviado         BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_notif_paciente ON notificaciones (paciente_id, fecha DESC);
