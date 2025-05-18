# database.py
import sqlite3
import os
from cryptography.fernet import Fernet
import base64
import json # Necesario para detalles_json en log_action
import traceback # Para log_action

# --- Configuration ---
DB_NAME = 'gastro_db_encrypted.sqlite'
KEY_FILE = 'secret.key'

# --- Cryptography Setup ---

def generate_key():
    key = Fernet.generate_key()
    with open(KEY_FILE, "wb") as key_file: key_file.write(key)
    print(f"New encryption key generated and saved to {KEY_FILE}")
    return key

def load_key():
    if not os.path.exists(KEY_FILE): return generate_key()
    try:
        with open(KEY_FILE, "rb") as key_file: key = key_file.read()
        if len(base64.urlsafe_b64decode(key)) != 32: raise ValueError("Invalid key format.")
        return key
    except Exception as e:
        print(f"Error loading key from {KEY_FILE}: {e}. Exiting."); exit(1)

ENCRYPTION_KEY = load_key()
FERNET_INSTANCE = Fernet(ENCRYPTION_KEY)

def encrypt_data(data):
    if data is None: return None
    # Asegurarse que data es string antes de codificar
    return FERNET_INSTANCE.encrypt(str(data).encode('utf-8'))

def decrypt_data(encrypted_data):
    if encrypted_data is None: return None
    try:
        # Asegurarse que encrypted_data es bytes
        if isinstance(encrypted_data, str):
             # Intentar decodificar si parece base64, aunque debería ser bytes desde la BD BLOB
             try:
                 encrypted_data_bytes = base64.urlsafe_b64decode(encrypted_data.encode('utf-8'))
             except Exception:
                 # Si no es base64 válido, podría ser un error o ya estar corrupto
                 print(f"Warning: Attempting to decrypt non-base64 string data.")
                 encrypted_data_bytes = encrypted_data.encode('utf-8') # Intentar de todos modos
        elif not isinstance(encrypted_data, bytes):
             # Si no es ni string ni bytes, convertir a string y luego a bytes
             print(f"Warning: Received non-bytes/non-string data for decryption: {type(encrypted_data)}. Converting.")
             encrypted_data_bytes = str(encrypted_data).encode('utf-8')
        else:
            encrypted_data_bytes = encrypted_data # Ya es bytes

        # Validar longitud mínima esperada para datos encriptados por Fernet
        # (esto es aproximado, pero evita errores con datos vacíos o muy cortos)
        if len(encrypted_data_bytes) < 20: 
             print(f"Warning: Received potentially invalid or too short encrypted data.")
             return "[Invalid Data]"

        return FERNET_INSTANCE.decrypt(encrypted_data_bytes).decode('utf-8')
    except base64.binascii.Error as b64e:
        print(f"Warning: Base64 decoding error during decryption - {b64e}. Data might be corrupted or not encrypted.")
        return "[Decryption/Base64 Error]"
    except ValueError as ve:
        print(f"Warning: Value error during decryption - {ve}. Data might be corrupted or not encrypted.")
        return "[Decryption/Value Error]"
    except Exception as e:
        # Captura cualquier otra excepción de decrypt, como InvalidToken
        print(f"Warning: Decryption failed - {e.__class__.__name__}: {e}. Data might be invalid or use a different key.")
        # traceback.print_exc() # Descomentar para depuración detallada
        return "[Decryption Error]"

# --- SQL Statements for Table Creation ---

# ***** MODIFICACIÓN AQUÍ *****
SQL_CREATE_USUARIOS = """
CREATE TABLE IF NOT EXISTS Usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_usuario TEXT NOT NULL UNIQUE, -- Mantener UNIQUE y no encriptado
    hash_contrasena TEXT NOT NULL,       -- Hash (correcto)
    nombre_completo BLOB,                -- Encriptado
    cedula BLOB UNIQUE,                  -- Cédula (Encriptada, UNIQUE)
    mpps TEXT UNIQUE,                    -- MPPS (No encriptado, UNIQUE, opcional) - Puede ser BLOB si se encripta
    especialidad TEXT,                   -- Especialidad (No encriptado)
    ruta_foto_perfil TEXT,               -- Ruta a la foto (No encriptado)
    rol TEXT NOT NULL CHECK(rol IN ('medico', 'administrador', 'enfermeria', 'otro')), -- Rol (No encriptado)
    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
    activo INTEGER DEFAULT 1 CHECK(activo IN (0, 1)) -- Estado (No encriptado)
);
"""
# El índice único para nombre_usuario ya está cubierto por UNIQUE en la tabla.
# Si quieres un índice específico adicional (aunque UNIQUE ya crea uno implícitamente):
# SQL_CREATE_USUARIOS_INDEX = """
# CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_nombre_usuario ON Usuarios(nombre_usuario);
# """
# Considera añadir índices para búsquedas frecuentes si es necesario (ej. por rol, mpps)
SQL_CREATE_USUARIOS_INDEX_ROL = """
CREATE INDEX IF NOT EXISTS idx_usuarios_rol ON Usuarios(rol);
"""
SQL_CREATE_USUARIOS_INDEX_MPPS = """
CREATE INDEX IF NOT EXISTS idx_usuarios_mpps ON Usuarios(mpps);
"""

# --- (Resto de las sentencias SQL y funciones como antes) ---

SQL_CREATE_PACIENTES = """
CREATE TABLE IF NOT EXISTS Pacientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero_historia TEXT UNIQUE NOT NULL,
    cedula BLOB UNIQUE,
    nombres BLOB NOT NULL,
    apellidos BLOB NOT NULL,
    sexo TEXT CHECK(sexo IN ('Femenino', 'Masculino', 'Otro')),
    fecha_nacimiento DATE,
    lugar_nacimiento BLOB,
    estado_civil BLOB,
    telefono_habitacion BLOB,
    telefono_movil BLOB,
    email BLOB,
    direccion BLOB,
    profesion_oficio BLOB,
    emerg_nombre BLOB,
    emerg_telefono BLOB,
    emerg_parentesco BLOB,
    emerg_direccion BLOB,
    fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP,
    usuario_registro_id INTEGER, 
    fecha_ultima_mod DATETIME,   
    usuario_ultima_mod_id INTEGER,
    notas_adicionales BLOB,
    ap_asma INTEGER DEFAULT 0 CHECK(ap_asma IN (0, 1)),
    ap_asma_detalle BLOB,
    ap_hta INTEGER DEFAULT 0 CHECK(ap_hta IN (0, 1)),
    ap_hta_detalle BLOB,
    ap_dm INTEGER DEFAULT 0 CHECK(ap_dm IN (0, 1)),
    ap_dm_detalle BLOB,
    ap_cardiopatia INTEGER DEFAULT 0 CHECK(ap_cardiopatia IN (0, 1)), 
    ap_cardiopatia_detalle BLOB,
    ap_alergias BLOB,
    ap_quirurgicos BLOB,
    ap_otros INTEGER DEFAULT 0 CHECK(ap_otros IN (0, 1)),
    ap_otros_detalle BLOB,
    af_madre BLOB,
    af_padre BLOB,
    af_hermanos BLOB,
    af_hijos BLOB,
    hab_tabaco BLOB,
    hab_alcohol BLOB,
    hab_drogas BLOB,
    hab_cafe BLOB,
    hab_perdida_peso BLOB,  -- <<< AÑADIR ESTA LÍNEA AQUÍ
    FOREIGN KEY (usuario_registro_id) REFERENCES Usuarios(id) ON DELETE SET NULL,
    FOREIGN KEY (usuario_ultima_mod_id) REFERENCES Usuarios(id) ON DELETE SET NULL
);
"""

SQL_CREATE_CONSULTAS = """
CREATE TABLE IF NOT EXISTS Consultas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id INTEGER NOT NULL,
    usuario_id INTEGER NOT NULL, -- Quién INICIÓ la consulta
    fecha_hora_ingreso DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_hora_egreso DATETIME,   -- Indica si está CERRADA
    usuario_cierre_id INTEGER,  -- Quién CERRÓ la consulta
    motivo_consulta BLOB NOT NULL,
    historia_enfermedad_actual BLOB NOT NULL,
    diagnostico_ingreso BLOB,
    fecha_ultima_mod DATETIME,   -- Última modificación de esta consulta
    usuario_ultima_mod_id INTEGER, -- Quién modificó por última vez
    FOREIGN KEY (paciente_id) REFERENCES Pacientes(id) ON DELETE CASCADE,
    FOREIGN KEY (usuario_id) REFERENCES Usuarios(id) ON DELETE RESTRICT,
    FOREIGN KEY (usuario_cierre_id) REFERENCES Usuarios(id) ON DELETE SET NULL,
    FOREIGN KEY (usuario_ultima_mod_id) REFERENCES Usuarios(id) ON DELETE SET NULL
);
"""

SQL_CREATE_EVOLUCIONES = """
CREATE TABLE IF NOT EXISTS Evoluciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    consulta_id INTEGER NOT NULL,
    usuario_id INTEGER NOT NULL, -- Quién CREÓ
    fecha_hora DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    dias_hospitalizacion INTEGER,
    ev_subjetivo BLOB,
    ev_objetivo BLOB,
    ev_ta BLOB,
    ev_fc INTEGER,
    ev_fr INTEGER,
    ev_sato2 INTEGER,
    ev_temp BLOB,
    ev_piel BLOB,
    ev_respiratorio BLOB,
    ev_cardiovascular BLOB,
    ev_abdomen BLOB,
    ev_extremidades BLOB,
    ev_neurologico BLOB,
    ev_otros BLOB,
    ev_diagnosticos BLOB,
    ev_tratamiento_plan BLOB,
    ev_comentario BLOB,
    fecha_ultima_mod DATETIME,    -- Última modificación de esta evolución
    usuario_ultima_mod_id INTEGER, -- Quién modificó por última vez
    FOREIGN KEY (consulta_id) REFERENCES Consultas(id) ON DELETE CASCADE,
    FOREIGN KEY (usuario_id) REFERENCES Usuarios(id) ON DELETE RESTRICT,
    FOREIGN KEY (usuario_ultima_mod_id) REFERENCES Usuarios(id) ON DELETE SET NULL
);
"""

SQL_CREATE_HISTORIAL_ACCIONES = """
CREATE TABLE IF NOT EXISTS HistorialAcciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_hora DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario_id INTEGER NOT NULL, -- Vuelve a ser NOT NULL
    tipo_accion VARCHAR(50) NOT NULL,
    tabla_afectada VARCHAR(50),
    registro_afectado_id INTEGER,
    descripcion TEXT NOT NULL,
    detalles_json TEXT,
    -- Restaurar la FOREIGN KEY
    FOREIGN KEY (usuario_id) REFERENCES Usuarios(id) ON DELETE CASCADE
);
"""
SQL_CREATE_HISTORIAL_INDEX_USER_DATE = """
CREATE INDEX IF NOT EXISTS idx_historial_usuario_fecha ON HistorialAcciones(usuario_id, fecha_hora);
"""
SQL_CREATE_HISTORIAL_INDEX_TYPE_DATE = """
CREATE INDEX IF NOT EXISTS idx_historial_tipo_fecha ON HistorialAcciones(tipo_accion, fecha_hora);
"""

SQL_CREATE_EXAMENES_FISICOS = """
CREATE TABLE IF NOT EXISTS ExamenesFisicos ( id INTEGER PRIMARY KEY AUTOINCREMENT, consulta_id INTEGER UNIQUE NOT NULL, fecha_hora DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, ef_ta BLOB, ef_fr INTEGER, ef_fc INTEGER, ef_sato2 INTEGER, ef_temp BLOB, ef_glic INTEGER, ef_piel BLOB, ef_respiratorio BLOB, ef_cardiovascular BLOB, ef_abdomen BLOB, ef_gastrointestinal BLOB, ef_genitourinario BLOB, ef_extremidades BLOB, ef_neurologico BLOB, ef_otros_hallazgos BLOB, FOREIGN KEY (consulta_id) REFERENCES Consultas(id) ON DELETE CASCADE );
"""

SQL_CREATE_ORDENES_MEDICAS = """
CREATE TABLE IF NOT EXISTS OrdenesMedicas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    consulta_id INTEGER NOT NULL,      -- A qué consulta pertenece esta orden (generalmente la activa)
    evolucion_id INTEGER,              -- Opcional: si la orden se generó desde una evolución específica
    usuario_id INTEGER NOT NULL,       -- Quién creó la orden
    fecha_hora DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    orden_json_blob BLOB NOT NULL,     -- Aquí irá el JSON encriptado con toda la estructura de la orden
    estado TEXT DEFAULT 'Pendiente'    -- Mantenemos estado para uso interno futuro si se necesita
        CHECK(estado IN ('Pendiente', 'Realizada', 'Cancelada', 'Parcial')),
    FOREIGN KEY (consulta_id) REFERENCES Consultas(id) ON DELETE CASCADE,
    FOREIGN KEY (evolucion_id) REFERENCES Evoluciones(id) ON DELETE SET NULL,
    FOREIGN KEY (usuario_id) REFERENCES Usuarios(id) ON DELETE RESTRICT
);
"""

SQL_CREATE_COMPLEMENTARIOS = """
CREATE TABLE IF NOT EXISTS Complementarios ( id INTEGER PRIMARY KEY AUTOINCREMENT, paciente_id INTEGER NOT NULL, consulta_id INTEGER, orden_medica_id INTEGER, usuario_registrador_id INTEGER NOT NULL, fecha_registro DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, tipo_complementario TEXT NOT NULL CHECK(tipo_complementario IN ('Laboratorio', 'Imagen', 'Patologia', 'Endoscopia', 'Otro')), nombre_estudio BLOB NOT NULL, fecha_realizacion DATETIME, resultado_informe BLOB NOT NULL, archivo_adjunto_path BLOB, FOREIGN KEY (paciente_id) REFERENCES Pacientes(id) ON DELETE CASCADE, FOREIGN KEY (consulta_id) REFERENCES Consultas(id) ON DELETE SET NULL, FOREIGN KEY (orden_medica_id) REFERENCES OrdenesMedicas(id) ON DELETE SET NULL, FOREIGN KEY (usuario_registrador_id) REFERENCES Usuarios(id) ON DELETE RESTRICT );
"""
SQL_CREATE_INTERCONSULTAS = """
CREATE TABLE IF NOT EXISTS Interconsultas ( id INTEGER PRIMARY KEY AUTOINCREMENT, paciente_id INTEGER NOT NULL, consulta_id INTEGER, orden_medica_id INTEGER, usuario_solicitante_id INTEGER NOT NULL, fecha_solicitud DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, servicio_consultado BLOB NOT NULL, motivo_consulta BLOB NOT NULL, fecha_respuesta DATETIME, usuario_respuesta_id INTEGER, respuesta_texto BLOB, estado TEXT DEFAULT 'Pendiente' CHECK(estado IN ('Pendiente', 'Respondida', 'Cancelada')), FOREIGN KEY (paciente_id) REFERENCES Pacientes(id) ON DELETE CASCADE, FOREIGN KEY (consulta_id) REFERENCES Consultas(id) ON DELETE SET NULL, FOREIGN KEY (orden_medica_id) REFERENCES OrdenesMedicas(id) ON DELETE SET NULL, FOREIGN KEY (usuario_solicitante_id) REFERENCES Usuarios(id) ON DELETE RESTRICT, FOREIGN KEY (usuario_respuesta_id) REFERENCES Usuarios(id) ON DELETE SET NULL );
"""
SQL_CREATE_INFORMES_MEDICOS = """
CREATE TABLE IF NOT EXISTS InformesMedicos ( id INTEGER PRIMARY KEY AUTOINCREMENT, paciente_id INTEGER NOT NULL, consulta_id INTEGER, usuario_id INTEGER NOT NULL, fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, tipo_informe TEXT NOT NULL CHECK(tipo_informe IN ('Alta', 'Resumen Historia', 'Procedimiento', 'Otro')), contenido_texto BLOB NOT NULL, archivo_generado_path BLOB, FOREIGN KEY (paciente_id) REFERENCES Pacientes(id) ON DELETE CASCADE, FOREIGN KEY (consulta_id) REFERENCES Consultas(id) ON DELETE SET NULL, FOREIGN KEY (usuario_id) REFERENCES Usuarios(id) ON DELETE RESTRICT );
"""
SQL_CREATE_RECIPES = """
CREATE TABLE IF NOT EXISTS Recipes ( id INTEGER PRIMARY KEY AUTOINCREMENT, paciente_id INTEGER NOT NULL, consulta_id INTEGER, evolucion_id INTEGER, usuario_id INTEGER NOT NULL, fecha_emision DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, tipo TEXT NOT NULL CHECK(tipo IN ('Tratamiento', 'Reposo', 'Indicaciones', 'Otro')), recipe_texto BLOB NOT NULL, FOREIGN KEY (paciente_id) REFERENCES Pacientes(id) ON DELETE CASCADE, FOREIGN KEY (consulta_id) REFERENCES Consultas(id) ON DELETE SET NULL, FOREIGN KEY (evolucion_id) REFERENCES Evoluciones(id) ON DELETE SET NULL, FOREIGN KEY (usuario_id) REFERENCES Usuarios(id) ON DELETE RESTRICT );
"""


# Lista de todas las sentencias CREATE TABLE y CREATE INDEX
ALL_TABLES_SQL = [
    SQL_CREATE_USUARIOS,              # Modificado
    # SQL_CREATE_USUARIOS_INDEX,      # El UNIQUE en la tabla es suficiente
    SQL_CREATE_USUARIOS_INDEX_ROL,    # Nuevo índice opcional
    SQL_CREATE_USUARIOS_INDEX_MPPS,   # Nuevo índice opcional
    SQL_CREATE_PACIENTES,
    SQL_CREATE_CONSULTAS,
    SQL_CREATE_EXAMENES_FISICOS,
    SQL_CREATE_EVOLUCIONES,
    SQL_CREATE_ORDENES_MEDICAS,
    SQL_CREATE_COMPLEMENTARIOS,
    SQL_CREATE_INTERCONSULTAS,
    SQL_CREATE_INFORMES_MEDICOS,
    SQL_CREATE_RECIPES,
    SQL_CREATE_HISTORIAL_ACCIONES,
    SQL_CREATE_HISTORIAL_INDEX_USER_DATE,
    SQL_CREATE_HISTORIAL_INDEX_TYPE_DATE
]

# --- Función Helper para Registrar Acción ---
def log_action(db_conn, usuario_id, tipo_accion, descripcion, tabla=None, registro_id=None, detalles=None):
    """Inserta un registro en la tabla HistorialAcciones. Asume que se llama dentro de una transacción."""
    if not db_conn or usuario_id is None: # Verificar ambos
        print("Error Log: Conexión BD o usuario_id faltante.")
        return

    print(f"LOG: User {usuario_id}, Action: {tipo_accion}, Desc: {descripcion[:100]}...")
    sql = """
        INSERT INTO HistorialAcciones
        (usuario_id, tipo_accion, tabla_afectada, registro_afectado_id, descripcion, detalles_json)
        VALUES (?, ?, ?, ?, ?, ?)
    """
    detalles_str = json.dumps(detalles) if detalles is not None else None
    try:
        cursor = db_conn.cursor()
        cursor.execute(sql, (usuario_id, tipo_accion, tabla, registro_id, descripcion, detalles_str))
    except Exception as e:
        print(f"!!! ERROR AL REGISTRAR ACCIÓN EN HISTORIAL: {e} !!!")
        traceback.print_exc()

# --- Funciones de Utilidad para la Base de Datos ---
def connect_db(db_name=DB_NAME):
    # ... (como antes) ...
    try:
        conn = sqlite3.connect(db_name)
        conn.execute("PRAGMA foreign_keys = 1;")
        return conn
    except sqlite3.Error as e:
        print(f"Error crítico al conectar BD '{db_name}': {e}"); exit(1)

def create_tables(conn):
    # ... (como antes) ...
    if not conn: return False
    try:
        cursor = conn.cursor()
        print("Creando/Verificando tablas e índices...")
        for statement in ALL_TABLES_SQL:
            # print(f"Ejecutando: {statement[:100]}...") # Descomentar para depurar
            cursor.execute(statement)
        # No hacemos commit aquí todavía, se hará después de añadir el log inicial si todo va bien.
        print("Tablas e índices definidos/verificados.")
        return True
    except sqlite3.Error as e:
        print(f"Error al crear tablas/índices: {e}");
        # No hacemos rollback aquí, lo hará initialize_database si falla create_tables
        return False
    # finally: # No cerramos cursor aquí, se necesita para log_action
    #     if cursor: cursor.close()

def initialize_database():
    print(f"Inicializando base de datos '{DB_NAME}'...")
    conn = None
    created_successfully = False
    try:
        conn = connect_db()
        if conn:
            print(f"Verificando/Creando tablas en '{DB_NAME}'...")
            # Usar 'with conn:' para manejo automático de transacción
            with conn:
                if create_tables(conn):
                    print("Tablas creadas/verificadas exitosamente.")
                    created_successfully = True
                else:
                    print("Fallo al crear/verificar tablas.")
                    # Rollback automático por el 'with conn:' si create_tables falla

            if created_successfully:
                print(f"Base de datos '{DB_NAME}' lista.")

    except sqlite3.Error as e_sql:
         print(f"Error de SQLite durante la inicialización: {e_sql}")
         traceback.print_exc()
    except Exception as e:
        print(f"Error general durante la inicialización: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
            print("Conexión de inicialización cerrada.")

    if not created_successfully:
         print("Fallo al inicializar BD.")

# --- Ejecución Principal (sin cambios) ---
if __name__ == "__main__":
    initialize_database()