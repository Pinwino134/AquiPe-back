-- =====================================================================
-- AquiPe - Esquema de base de datos (PostgreSQL 13+)
-- Pagos fuera de la app: solo se registra el precio acordado.
-- Convenciones:
--   * UUID para datos que crean los usuarios (permite sincronizar offline).
--   * Identidad entera para catálogos (zona, categoria).
--   * Fechas en timestamptz. Borrado lógico en publicacion (deleted_at).
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid() en PG < 13

-- ---------------------------------------------------------------------
-- 1. TIPOS ENUMERADOS
-- ---------------------------------------------------------------------
CREATE TYPE estado_usuario        AS ENUM ('ACTIVO', 'SUSPENDIDO', 'ELIMINADO');
CREATE TYPE tipo_publicacion      AS ENUM ('SERVICIO', 'FAVOR', 'RECURSO', 'EMERGENCIA');
CREATE TYPE direccion_publicacion AS ENUM ('SOLICITA', 'OFRECE');
CREATE TYPE estado_publicacion    AS ENUM ('ABIERTA', 'PAUSADA', 'ASIGNADA', 'EN_CURSO',
                                           'COMPLETADA', 'CANCELADA', 'EXPIRADA');
CREATE TYPE tipo_precio           AS ENUM ('FIJO', 'POR_HORA', 'A_CONVENIR');
CREATE TYPE modalidad_servicio    AS ENUM ('DOMICILIO', 'VIRTUAL', 'EN_LOCAL');
CREATE TYPE nivel_urgencia        AS ENUM ('BAJA', 'MEDIA', 'ALTA', 'CRITICA');
CREATE TYPE estado_respuesta      AS ENUM ('ENVIADA', 'ACEPTADA', 'RECHAZADA', 'RETIRADA');
CREATE TYPE estado_acuerdo        AS ENUM ('PROGRAMADO', 'EN_CURSO', 'COMPLETADO', 'CANCELADO');
CREATE TYPE estado_coincidencia   AS ENUM ('SUGERIDA', 'DESCARTADA', 'CONTACTO_SOLICITADO');
CREATE TYPE tipo_notificacion     AS ENUM ('RESPUESTA_RECIBIDA', 'RESPUESTA_ACEPTADA',
                                           'RESPUESTA_RECHAZADA', 'ACUERDO_ACTUALIZADO',
                                           'RESENA_RECIBIDA', 'COINCIDENCIA_NUEVA',
                                           'EMERGENCIA_CERCANA', 'SISTEMA');
CREATE TYPE plataforma_dispositivo AS ENUM ('ANDROID', 'IOS', 'WEB');
CREATE TYPE estado_reporte        AS ENUM ('PENDIENTE', 'REVISADO', 'DESCARTADO', 'ACCION_TOMADA');

-- ---------------------------------------------------------------------
-- 2. CATÁLOGOS
-- ---------------------------------------------------------------------
CREATE TABLE zona (
    id        integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre    varchar(100) NOT NULL,
    distrito  varchar(100) NOT NULL,
    ciudad    varchar(100) NOT NULL DEFAULT 'Arequipa',
    latitud   numeric(9,6) NOT NULL CHECK (latitud  BETWEEN -90  AND 90),
    longitud  numeric(9,6) NOT NULL CHECK (longitud BETWEEN -180 AND 180),
    UNIQUE (nombre, distrito, ciudad)
);

CREATE TABLE categoria (
    id        integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre    varchar(80) NOT NULL,
    icono     varchar(50),
    color     varchar(9),
    padre_id  integer REFERENCES categoria(id) ON DELETE RESTRICT,
    aplica_a  tipo_publicacion[] NOT NULL,
    activa    boolean NOT NULL DEFAULT true
);
CREATE UNIQUE INDEX ux_categoria_nombre
    ON categoria (COALESCE(padre_id, 0), lower(nombre));

-- ---------------------------------------------------------------------
-- 3. USUARIOS Y SEGURIDAD
-- ---------------------------------------------------------------------
CREATE TABLE usuario (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre_completo         varchar(120) NOT NULL,
    correo                  varchar(160) NOT NULL,
    telefono                varchar(20)  NOT NULL,
    password_hash           varchar(255) NOT NULL,          -- argon2 / bcrypt
    foto_url                text,
    zona_id                 integer REFERENCES zona(id),
    latitud                 numeric(9,6) CHECK (latitud  BETWEEN -90  AND 90),
    longitud                numeric(9,6) CHECK (longitud BETWEEN -180 AND 180),
    perfil_publico          boolean NOT NULL DEFAULT true,
    notificaciones_activas  boolean NOT NULL DEFAULT true,
    estado                  estado_usuario NOT NULL DEFAULT 'ACTIVO',
    calificacion_promedio   numeric(3,2) NOT NULL DEFAULT 0 CHECK (calificacion_promedio BETWEEN 0 AND 5),
    total_resenas           integer NOT NULL DEFAULT 0 CHECK (total_resenas >= 0),
    correo_verificado_at    timestamptz,
    telefono_verificado_at  timestamptz,
    ultimo_acceso_at        timestamptz,
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_usuario_coords CHECK ((latitud IS NULL) = (longitud IS NULL))
);
CREATE UNIQUE INDEX ux_usuario_correo   ON usuario (lower(correo));
CREATE UNIQUE INDEX ux_usuario_telefono ON usuario (telefono);

-- Datos extra de quien ofrece servicios (se crea cuando el usuario activa "ofrecer servicios")
CREATE TABLE perfil_proveedor (
    usuario_id         uuid PRIMARY KEY REFERENCES usuario(id) ON DELETE CASCADE,
    biografia          varchar(500),
    anios_experiencia  smallint CHECK (anios_experiencia BETWEEN 0 AND 80),
    disponibilidad     varchar(200),          -- ej. "Lun-Vie 8:00-18:00"
    verificado         boolean NOT NULL DEFAULT false,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE sesion (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id          uuid NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    refresh_token_hash  varchar(255) NOT NULL UNIQUE,
    dispositivo         varchar(120),
    expira_at           timestamptz NOT NULL,
    revocada_at         timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE token_recuperacion (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id  uuid NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    token_hash  varchar(255) NOT NULL UNIQUE,
    expira_at   timestamptz NOT NULL,
    usado_at    timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE dispositivo_push (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id       uuid NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    expo_push_token  varchar(255) NOT NULL UNIQUE,
    plataforma       plataforma_dispositivo NOT NULL,
    activo           boolean NOT NULL DEFAULT true,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 4. RECURSOS PERSONALES (Perfil > Mis recursos disponibles)
-- ---------------------------------------------------------------------
CREATE TABLE recurso (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id   uuid NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    nombre       varchar(100) NOT NULL,
    descripcion  varchar(300),
    cantidad     integer NOT NULL DEFAULT 1 CHECK (cantidad > 0),
    unidad       varchar(30),                       -- unidad, kit, libros...
    disponible   boolean NOT NULL DEFAULT true,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 5. PUBLICACIONES (servicios, favores, recursos, emergencias)
--    direccion = SOLICITA -> "necesito / solicitar"
--    direccion = OFRECE   -> "ofrezco / ayudar"
-- ---------------------------------------------------------------------
CREATE TABLE publicacion (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    autor_id      uuid NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    tipo          tipo_publicacion      NOT NULL,
    direccion     direccion_publicacion NOT NULL,
    categoria_id  integer REFERENCES categoria(id),
    titulo        varchar(80)  NOT NULL,
    descripcion   varchar(1000) NOT NULL,
    zona_id       integer REFERENCES zona(id),
    latitud       numeric(9,6) CHECK (latitud  BETWEEN -90  AND 90),
    longitud      numeric(9,6) CHECK (longitud BETWEEN -180 AND 180),
    recurso_id    uuid REFERENCES recurso(id) ON DELETE SET NULL,
    estado        estado_publicacion NOT NULL DEFAULT 'ABIERTA',
    expira_at     timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    deleted_at    timestamptz,
    UNIQUE (id, tipo),                                       -- soporta los FK de detalle_*
    CONSTRAINT ck_pub_coords    CHECK ((latitud IS NULL) = (longitud IS NULL)),
    CONSTRAINT ck_pub_emergencia CHECK (tipo <> 'EMERGENCIA' OR latitud IS NOT NULL)
);

-- Detalle de SERVICIO: sirve para ofrecer servicios y para solicitudes de trabajo
CREATE TABLE detalle_servicio (
    publicacion_id   uuid PRIMARY KEY,
    tipo             tipo_publicacion NOT NULL DEFAULT 'SERVICIO' CHECK (tipo = 'SERVICIO'),
    -- Si OFRECE: precio del servicio
    tipo_precio      tipo_precio NOT NULL DEFAULT 'A_CONVENIR',
    monto            numeric(10,2) CHECK (monto >= 0),
    moneda           char(3) NOT NULL DEFAULT 'PEN',
    modalidad        modalidad_servicio NOT NULL DEFAULT 'DOMICILIO',
    radio_km         numeric(5,2) CHECK (radio_km > 0),
    disponibilidad   varchar(200),
    -- Si SOLICITA: presupuesto y plazo de la solicitud de trabajo
    presupuesto_min  numeric(10,2) CHECK (presupuesto_min >= 0),
    presupuesto_max  numeric(10,2) CHECK (presupuesto_max >= 0),
    fecha_requerida  timestamptz,
    urgencia         nivel_urgencia NOT NULL DEFAULT 'MEDIA',
    FOREIGN KEY (publicacion_id, tipo) REFERENCES publicacion (id, tipo) ON DELETE CASCADE,
    CONSTRAINT ck_ds_monto  CHECK (tipo_precio = 'A_CONVENIR' OR monto IS NOT NULL),
    CONSTRAINT ck_ds_presup CHECK (presupuesto_max IS NULL OR presupuesto_min IS NULL
                                   OR presupuesto_max >= presupuesto_min)
);

-- Detalle de EMERGENCIA
CREATE TABLE detalle_emergencia (
    publicacion_id   uuid PRIMARY KEY,
    tipo             tipo_publicacion NOT NULL DEFAULT 'EMERGENCIA' CHECK (tipo = 'EMERGENCIA'),
    cantidad         integer CHECK (cantidad > 0),          -- obligatoria si OFRECE (lo valida el backend)
    unidad           varchar(30),
    detalle_cantidad varchar(200),                          -- "20 botellas de agua y 15 paquetes"
    nivel_urgencia   nivel_urgencia NOT NULL DEFAULT 'ALTA',
    vigente_hasta    timestamptz,
    FOREIGN KEY (publicacion_id, tipo) REFERENCES publicacion (id, tipo) ON DELETE CASCADE
);

CREATE TABLE publicacion_adjunto (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    publicacion_id uuid NOT NULL REFERENCES publicacion(id) ON DELETE CASCADE,
    url            text NOT NULL,
    orden          smallint NOT NULL DEFAULT 0,
    created_at     timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 6. RESPUESTAS, ACUERDOS Y RESEÑAS
-- ---------------------------------------------------------------------
-- Alguien responde a una publicación: propuesta a una solicitud de trabajo,
-- contratación de un servicio ofrecido, "ofrecer mi ayuda", "solicitar contacto".
CREATE TABLE respuesta (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    publicacion_id   uuid NOT NULL REFERENCES publicacion(id) ON DELETE CASCADE,
    usuario_id       uuid NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    mensaje          varchar(500) NOT NULL,
    precio_propuesto numeric(10,2) CHECK (precio_propuesto >= 0),
    estado           estado_respuesta NOT NULL DEFAULT 'ENVIADA',
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (publicacion_id, usuario_id)
);

-- Trabajo o favor acordado (nace al aceptar una respuesta). Sin datos de pago.
CREATE TABLE acuerdo (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    publicacion_id      uuid NOT NULL REFERENCES publicacion(id) ON DELETE CASCADE,
    respuesta_id        uuid NOT NULL UNIQUE REFERENCES respuesta(id) ON DELETE RESTRICT,
    solicitante_id      uuid NOT NULL REFERENCES usuario(id),
    proveedor_id        uuid NOT NULL REFERENCES usuario(id),
    precio_acordado     numeric(10,2) CHECK (precio_acordado >= 0),   -- referencial; se paga fuera de la app
    estado              estado_acuerdo NOT NULL DEFAULT 'PROGRAMADO',
    fecha_programada    timestamptz,
    completado_at       timestamptz,
    cancelado_at        timestamptz,
    motivo_cancelacion  varchar(300),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_acuerdo_partes CHECK (solicitante_id <> proveedor_id)
);

CREATE TABLE resena (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    acuerdo_id       uuid NOT NULL REFERENCES acuerdo(id) ON DELETE CASCADE,
    autor_id         uuid NOT NULL REFERENCES usuario(id),
    destinatario_id  uuid NOT NULL REFERENCES usuario(id),
    calificacion     smallint NOT NULL CHECK (calificacion BETWEEN 1 AND 5),
    comentario       varchar(500),
    created_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (acuerdo_id, autor_id),
    CONSTRAINT ck_resena_partes CHECK (autor_id <> destinatario_id)
);

-- ---------------------------------------------------------------------
-- 7. COINCIDENCIAS (pantalla "Coincidencias")
-- ---------------------------------------------------------------------
CREATE TABLE coincidencia (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    solicitud_id        uuid NOT NULL REFERENCES publicacion(id) ON DELETE CASCADE,
    oferta_id           uuid NOT NULL REFERENCES publicacion(id) ON DELETE CASCADE,
    usuario_destino_id  uuid NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    puntaje             numeric(5,2) NOT NULL DEFAULT 0,
    estado              estado_coincidencia NOT NULL DEFAULT 'SUGERIDA',
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (solicitud_id, oferta_id, usuario_destino_id),
    CONSTRAINT ck_coinc_distintas CHECK (solicitud_id <> oferta_id)
);

-- ---------------------------------------------------------------------
-- 8. NOTIFICACIONES Y MODERACIÓN
-- ---------------------------------------------------------------------
CREATE TABLE notificacion (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id  uuid NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    tipo        tipo_notificacion NOT NULL,
    titulo      varchar(120) NOT NULL,
    cuerpo      varchar(300),
    ref_tipo    varchar(30),            -- 'publicacion', 'respuesta', 'acuerdo'...
    ref_id      uuid,
    leida_at    timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE reporte (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    reportante_id       uuid NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    publicacion_id      uuid REFERENCES publicacion(id) ON DELETE CASCADE,
    usuario_reportado_id uuid REFERENCES usuario(id) ON DELETE CASCADE,
    motivo              varchar(60) NOT NULL,
    detalle             varchar(500),
    estado              estado_reporte NOT NULL DEFAULT 'PENDIENTE',
    created_at          timestamptz NOT NULL DEFAULT now(),
    resuelto_at         timestamptz,
    CONSTRAINT ck_reporte_objetivo CHECK (num_nonnulls(publicacion_id, usuario_reportado_id) = 1)
);

CREATE TABLE bloqueo (
    usuario_id    uuid NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    bloqueado_id  uuid NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    created_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (usuario_id, bloqueado_id),
    CONSTRAINT ck_bloqueo_distintos CHECK (usuario_id <> bloqueado_id)
);

-- ---------------------------------------------------------------------
-- 9. ÍNDICES
-- ---------------------------------------------------------------------
CREATE INDEX ix_pub_feed      ON publicacion (tipo, direccion, estado, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX ix_pub_categoria ON publicacion (categoria_id)  WHERE deleted_at IS NULL;
CREATE INDEX ix_pub_zona      ON publicacion (zona_id)       WHERE deleted_at IS NULL;
CREATE INDEX ix_pub_autor     ON publicacion (autor_id);
CREATE INDEX ix_pub_coords    ON publicacion (latitud, longitud) WHERE latitud IS NOT NULL;
CREATE INDEX ix_respuesta_usuario ON respuesta (usuario_id, estado);
CREATE INDEX ix_acuerdo_solic ON acuerdo (solicitante_id, estado);
CREATE INDEX ix_acuerdo_prov  ON acuerdo (proveedor_id, estado);
CREATE INDEX ix_resena_dest   ON resena (destinatario_id);
CREATE INDEX ix_coinc_destino ON coincidencia (usuario_destino_id, estado);
CREATE INDEX ix_notif_usuario ON notificacion (usuario_id, leida_at, created_at DESC);
CREATE INDEX ix_recurso_usuario ON recurso (usuario_id);
CREATE INDEX ix_sesion_usuario  ON sesion (usuario_id);

-- ---------------------------------------------------------------------
-- 10. FUNCIONES Y TRIGGERS
-- ---------------------------------------------------------------------

-- 10.1 updated_at automático
CREATE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['usuario','perfil_proveedor','dispositivo_push','recurso',
                             'publicacion','respuesta','acuerdo','coincidencia']
    LOOP
        EXECUTE format('CREATE TRIGGER trg_%1$s_updated BEFORE UPDATE ON %1$I
                        FOR EACH ROW EXECUTE FUNCTION set_updated_at()', t);
    END LOOP;
END $$;

-- 10.2 Reglas de respuesta: no responder a la propia publicación,
--      publicación abierta, y una sola respuesta aceptada en solicitudes (SOLICITA)
CREATE FUNCTION validar_respuesta() RETURNS trigger AS $$
DECLARE p publicacion%ROWTYPE;
BEGIN
    SELECT * INTO p FROM publicacion WHERE id = NEW.publicacion_id;

    IF TG_OP = 'INSERT' THEN
        IF p.autor_id = NEW.usuario_id THEN
            RAISE EXCEPTION 'No puedes responder a tu propia publicación';
        END IF;
        IF p.estado <> 'ABIERTA' OR p.deleted_at IS NOT NULL THEN
            RAISE EXCEPTION 'La publicación no está abierta';
        END IF;
    END IF;

    IF NEW.estado = 'ACEPTADA' AND p.direccion = 'SOLICITA' AND
       EXISTS (SELECT 1 FROM respuesta
               WHERE publicacion_id = NEW.publicacion_id
                 AND estado = 'ACEPTADA' AND id <> NEW.id) THEN
        RAISE EXCEPTION 'La solicitud ya tiene una respuesta aceptada';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_respuesta_validar
    BEFORE INSERT OR UPDATE OF estado ON respuesta
    FOR EACH ROW EXECUTE FUNCTION validar_respuesta();

-- 10.3 Reseñas: solo entre las partes de un acuerdo COMPLETADO
CREATE FUNCTION validar_resena() RETURNS trigger AS $$
DECLARE a acuerdo%ROWTYPE;
BEGIN
    SELECT * INTO a FROM acuerdo WHERE id = NEW.acuerdo_id;
    IF a.estado <> 'COMPLETADO' THEN
        RAISE EXCEPTION 'Solo se puede reseñar un acuerdo completado';
    END IF;
    IF NOT ((NEW.autor_id = a.solicitante_id AND NEW.destinatario_id = a.proveedor_id) OR
            (NEW.autor_id = a.proveedor_id   AND NEW.destinatario_id = a.solicitante_id)) THEN
        RAISE EXCEPTION 'La reseña debe ser entre las partes del acuerdo';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_resena_validar
    BEFORE INSERT ON resena
    FOR EACH ROW EXECUTE FUNCTION validar_resena();

-- 10.4 Mantener calificacion_promedio y total_resenas en usuario
CREATE FUNCTION actualizar_reputacion() RETURNS trigger AS $$
DECLARE uid uuid;
BEGIN
    uid := COALESCE(NEW.destinatario_id, OLD.destinatario_id);
    UPDATE usuario u
       SET calificacion_promedio = COALESCE((SELECT round(avg(calificacion)::numeric, 2)
                                             FROM resena WHERE destinatario_id = uid), 0),
           total_resenas         = (SELECT count(*) FROM resena WHERE destinatario_id = uid)
     WHERE u.id = uid;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_resena_reputacion
    AFTER INSERT OR UPDATE OR DELETE ON resena
    FOR EACH ROW EXECUTE FUNCTION actualizar_reputacion();

-- 10.5 Distancia en km (Haversine). Si activas PostGIS, reemplázala por ST_DWithin.
CREATE FUNCTION distancia_km(lat1 numeric, lon1 numeric, lat2 numeric, lon2 numeric)
RETURNS numeric AS $$
    SELECT (6371 * 2 * asin(sqrt(
              power(sin(radians((lat2 - lat1) / 2)), 2) +
              cos(radians(lat1)) * cos(radians(lat2)) *
              power(sin(radians((lon2 - lon1) / 2)), 2)
           )))::numeric;
$$ LANGUAGE sql IMMUTABLE;

-- ---------------------------------------------------------------------
-- 11. DATOS INICIALES
-- ---------------------------------------------------------------------
INSERT INTO zona (nombre, distrito, latitud, longitud) VALUES
    ('Cercado',   'Arequipa',   -16.398900, -71.535000),
    ('Yanahuara', 'Yanahuara',  -16.391000, -71.543000),
    ('Cayma',     'Cayma',      -16.383000, -71.548000);

INSERT INTO categoria (nombre, icono, aplica_a) VALUES
    ('Hogar',       'home',      '{SERVICIO}'),
    ('Educación',   'book',      '{SERVICIO,FAVOR}'),
    ('Tecnología',  'laptop',    '{SERVICIO,FAVOR}'),
    ('Salud',       'medkit',    '{SERVICIO}'),
    ('Seguridad',   'videocam',  '{SERVICIO}'),
    ('Herramienta', 'build',     '{FAVOR,RECURSO}'),
    ('Apoyo',       'people',    '{FAVOR}'),
    ('Donación',    'cube',      '{FAVOR,RECURSO}'),
    ('Otro',        'grid',      '{SERVICIO,FAVOR,RECURSO}'),
    ('Agua y alimentos',  'water',        '{EMERGENCIA}'),
    ('Primeros auxilios', 'medkit',       '{EMERGENCIA}'),
    ('Apoyo a personas',  'alert-circle', '{EMERGENCIA}');

-- ---------------------------------------------------------------------
-- 12. EJEMPLO: publicaciones cercanas para el mapa (radio 3 km)
-- ---------------------------------------------------------------------
-- SELECT p.id, p.titulo, p.tipo, p.direccion,
--        distancia_km(-16.3989, -71.535, p.latitud, p.longitud) AS km
--   FROM publicacion p
--  WHERE p.deleted_at IS NULL AND p.estado = 'ABIERTA'
--    AND p.latitud  BETWEEN -16.3989 - 0.03 AND -16.3989 + 0.03
--    AND p.longitud BETWEEN -71.535  - 0.03 AND -71.535  + 0.03
--    AND distancia_km(-16.3989, -71.535, p.latitud, p.longitud) <= 3
--  ORDER BY km;
