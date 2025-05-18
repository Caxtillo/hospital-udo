# auth.py
import bcrypt
import sqlite3
import traceback # Para errores de log
from database import connect_db, decrypt_data, encrypt_data, log_action # Importar log_action

SALT_ROUNDS = 12

def hash_password(password):
    # ... (sin cambios) ...
    if not password:
        raise ValueError("La contraseña no puede estar vacía")
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt(rounds=SALT_ROUNDS)
    hashed_pw = bcrypt.hashpw(password_bytes, salt)
    return hashed_pw.decode('utf-8')

def verify_password(stored_hash, provided_password):
    # ... (sin cambios) ...
    if not stored_hash or not provided_password:
        return False
    stored_hash_bytes = stored_hash.encode('utf-8')
    provided_password_bytes = provided_password.encode('utf-8')
    try:
        return bcrypt.checkpw(provided_password_bytes, stored_hash_bytes)
    except ValueError:
        print("Error: Hash de contraseña almacenado inválido.")
        return False
    except Exception as e:
        print(f"Error inesperado durante la verificación de contraseña: {e}")
        return False

def verify_user_login(username, password):
    # ... (sin cambios en la lógica de verificación) ...
    conn = connect_db()
    if not conn: return None
    user_data = None
    cursor = None
    try:
        cursor = conn.cursor()
        # Usar nombre_usuario (TEXT) para buscar
        cursor.execute("""
            SELECT id, nombre_usuario, hash_contrasena, nombre_completo, rol, activo 
            FROM Usuarios 
            WHERE nombre_usuario = ? AND activo = 1
            """, (username,))
        user_record = cursor.fetchone()

        if user_record:
            user_id, db_username, stored_hash, nombre_completo_enc, rol, activo = user_record
            if verify_password(stored_hash, password):
                nombre_completo = decrypt_data(nombre_completo_enc) if nombre_completo_enc else None
                user_data = {
                    'id': user_id,
                    'username': db_username,
                    'full_name': nombre_completo,
                    'role': rol
                    # Podrías añadir otros campos no sensibles aquí si los necesitas en la sesión
                    # 'especialidad': especialidad, 
                }
    except sqlite3.Error as e:
        print(f"Error de base de datos al verificar usuario: {e}")
    except Exception as e:
        print(f"Error inesperado al verificar usuario: {e}")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    return user_data


# --- MODIFICACIÓN EN create_test_user ---
def create_test_user():
    """Asegura la existencia del usuario admin y registra el evento SISTEMA_INIT si no existe."""
    conn = None
    admin_user_id = None
    is_new_user = False
    try:
        conn = connect_db()
        if not conn: return
        
        test_username = "admin"
        test_password = "admin"
        
        with conn: # Manejo automático de transacción
            cursor = conn.cursor()

            # 1. Verificar/Crear usuario admin
            cursor.execute("SELECT id FROM Usuarios WHERE nombre_usuario = ?", (test_username,))
            existing_user = cursor.fetchone()

            if existing_user:
                admin_user_id = existing_user[0]
                print(f"Usuario de prueba '{test_username}' (ID: {admin_user_id}) ya existe.")
            else:
                print(f"Creando usuario de prueba '{test_username}'...")
                hashed_pw = hash_password(test_password)
                encrypted_fullname = encrypt_data("Administrador Principal")
                # Insertar con valores por defecto o None para las nuevas columnas
                cursor.execute("""
                    INSERT INTO Usuarios 
                    (nombre_usuario, hash_contrasena, nombre_completo, cedula, mpps, especialidad, ruta_foto_perfil, rol, activo) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, 
                    (test_username, hashed_pw, encrypted_fullname, None, None, None, None, 'administrador', 1))
                admin_user_id = cursor.lastrowid # Obtener el ID del admin recién creado
                is_new_user = True
                print(f"Usuario de prueba '{test_username}' creado con ID: {admin_user_id}.")

            # 2. Verificar si ya existe un log de SISTEMA_INIT
            cursor.execute("SELECT 1 FROM HistorialAcciones WHERE tipo_accion = ? LIMIT 1", ("SISTEMA_INIT",))
            init_log_exists = cursor.fetchone()

            # 3. Si el log NO existe Y tenemos un ID de admin, añadir el log
            if not init_log_exists and admin_user_id is not None:
                print(f"Registrando evento SISTEMA_INIT asociado al usuario admin (ID: {admin_user_id})...")
                log_action(
                    db_conn=conn, # Usar la conexión existente dentro de la transacción 'with'
                    usuario_id=admin_user_id,
                    tipo_accion="SISTEMA_INIT",
                    descripcion=f"Sistema inicializado. Usuario admin '{test_username}' asegurado.",
                    detalles={'evento': 'inicializacion_post_creacion_admin'}
                )
                print("Evento SISTEMA_INIT registrado.")
            elif init_log_exists:
                 print("Info: Evento SISTEMA_INIT ya existe en el historial.")

            # El commit es automático al salir del 'with conn:' si no hay excepciones

    except sqlite3.Error as e:
        print(f"Error de SQLite en create_test_user: {e}")
        traceback.print_exc() # El rollback es automático
    except ValueError as e:
        print(f"Error de valor en create_test_user (ej. contraseña vacía): {e}")
        traceback.print_exc() # El rollback es automático
    except Exception as e:
         print(f"Error general en create_test_user: {e}")
         traceback.print_exc() # El rollback es automático
    finally:
        if conn:
            conn.close()
            print("Conexión create_test_user cerrada.")


if __name__ == "__main__":
    # Al ejecutar auth.py directamente, primero inicializa la DB y luego asegura el usuario
    import database
    database.initialize_database() 
    create_test_user()