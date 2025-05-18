# medico_acciones.py
import sqlite3
import traceback
import os # Necesario para manejar rutas de fotos
import database
from auth import hash_password # Reutilizamos la función de hash
from database import log_action # Para auditoría
from datetime import datetime # Para futura lógica de modificación

class MedicoActions:

    def _generate_username(self, nombre_completo, cedula):
        """Genera un username inicial: primernombre + ultimos 3 cedula."""
        # Usar nombre_completo para obtener primer nombre
        try:
            nombres = nombre_completo.split()
            primer_nombre = nombres[0].lower().strip() if nombres else 'user'
            # Limpiar caracteres no alfanuméricos
            primer_nombre_limpio = "".join(c for c in primer_nombre if c.isalnum())
            if not primer_nombre_limpio: primer_nombre_limpio = 'user'

            # Usar últimos 3 de la cédula SIN V/E-
            cedula_numeros = "".join(filter(str.isdigit, cedula or ''))
            ultimos_cedula = cedula_numeros[-3:] if len(cedula_numeros) >= 3 else cedula_numeros
            if not ultimos_cedula: ultimos_cedula = '000'

            username_base = f"{primer_nombre_limpio}{ultimos_cedula}"

            # --- Verificación de Unicidad (Recomendado) ---
            # Deberíamos verificar aquí si el username ya existe y añadir un número si es necesario
            # conn_check = None
            # try:
            #     conn_check = database.connect_db()
            #     cursor_check = conn_check.cursor()
            #     base_query = "SELECT 1 FROM Usuarios WHERE nombre_usuario = ?"
            #     suffix = 0
            #     final_username = username_base
            #     while cursor_check.execute(base_query, (final_username,)).fetchone():
            #         suffix += 1
            #         final_username = f"{username_base}{suffix}"
            #     username_base = final_username
            # except Exception as e_check:
            #      print(f"Advertencia: Error verificando unicidad de username: {e_check}")
            # finally:
            #     if conn_check: conn_check.close()
            # --- Fin Verificación ---

            print(f"MedicoActions: Username generado: {username_base}")
            return username_base
        except Exception as e:
            print(f"MedicoActions Error generando username: {e}")
            return f"erroruser{datetime.now().strftime('%S%f')}" # Fallback más único

    def add_new(self, medico_data, current_user_id):
        """
        Añade un nuevo usuario (médico u otro rol) a la base de datos.
        Incluye los nuevos campos: cedula, mpps, especialidad, ruta_foto_perfil.
        Retorna: tuple (bool: success, str: message)
        """
        print(f"MedicoActions: Iniciando añadir nuevo usuario/medico: {medico_data.get('nombre_completo')}")

        # Obtener datos del diccionario (frontend)
        nombre_completo = medico_data.get('nombre_completo')
        cedula = medico_data.get('cedula') # Ej: "V-12345678"
        mpps = medico_data.get('mpps')
        especialidad = medico_data.get('especialidad')
        # La ruta real vendría del backend después de guardar el archivo. El frontend solo envía placeholder o nada.
        ruta_foto_perfil = medico_data.get('ruta_foto_perfil') # Campo oculto que llenaría el backend
        nombre_usuario_propuesto = medico_data.get('nombre_usuario') # El que sugiere/escribe el usuario
        contrasena_inicial = medico_data.get('contrasena') # La que escribe el usuario
        rol = medico_data.get('rol')
        activo = int(medico_data.get('activo', 1)) # Convertir a int (0 o 1)

        # --- Validaciones ---
        if not nombre_completo or not cedula or not nombre_usuario_propuesto or not contrasena_inicial or not rol:
            return False, "Error: Nombre Completo, Cédula, Nombre de Usuario, Contraseña Inicial y Rol son requeridos."
        
        # Validar formato cédula (básico)
        if not isinstance(cedula, str) or not (cedula.upper().startswith('V-') or cedula.upper().startswith('E-')) or not any(char.isdigit() for char in cedula):
             return False, "Error: Formato de Cédula inválido (Ej: V-12345678 o E-12345678)."
             
        # Validar contraseña mínima
        if len(contrasena_inicial) < 4:
             return False, "Error: La contraseña inicial debe tener al menos 4 caracteres."

        # Usar el username propuesto por el usuario
        username = nombre_usuario_propuesto.strip().lower() # Usar minúsculas y sin espacios

        # Hashear la contraseña proporcionada
        hashed_pw = hash_password(contrasena_inicial)

        conn = None
        try:
            conn = database.connect_db()
            # Usar 'with conn:' para manejo automático de transacción
            with conn:
                cursor = conn.cursor()

                print(f"MedicoActions: Preparando INSERT para Usuario: {username}")
                
                # Encriptar datos sensibles
                nombre_completo_enc = database.encrypt_data(nombre_completo)
                cedula_enc = database.encrypt_data(cedula) 

                sql = """
                    INSERT INTO Usuarios (
                        nombre_usuario, hash_contrasena, nombre_completo, 
                        cedula, mpps, especialidad, ruta_foto_perfil, 
                        rol, activo 
                        -- fecha_creacion es DEFAULT
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                values = (
                    username, hashed_pw, nombre_completo_enc,
                    cedula_enc, mpps, especialidad, ruta_foto_perfil,
                    rol, activo
                )

                cursor.execute(sql, values)
                new_user_id = cursor.lastrowid
                print(f"MedicoActions: Usuario insertado con ID: {new_user_id}, Username: {username}")

                # Registrar Acción
                log_descripcion = f"Usuario ID {current_user_id} creó nuevo usuario '{username}' (ID: {new_user_id}, Rol: {rol})."
                log_action(conn, current_user_id, 'CREAR_USUARIO', log_descripcion,
                           tabla='Usuarios', registro_id=new_user_id, 
                           detalles={'nombre_completo': nombre_completo, 'cedula': cedula, 'rol': rol}) # Añadir más detalles

                # Commit es automático al salir del 'with conn:' si no hay excepciones
                
            print("MedicoActions: Transacción completada.")
            # No retornar contraseña en mensaje de éxito por seguridad
            return True, f"Usuario '{username}' creado exitosamente."

        except sqlite3.IntegrityError as e:
             print(f"MedicoActions DB Integrity Error: {e}")
             # Rollback es automático con 'with conn:'
             if "UNIQUE constraint failed: Usuarios.nombre_usuario" in str(e):
                 return False, f"Error: El nombre de usuario '{username}' ya existe. Por favor, elija otro."
             elif "UNIQUE constraint failed: Usuarios.cedula" in str(e):
                  return False, f"Error: La cédula '{cedula}' ya está registrada para otro usuario."
             elif "UNIQUE constraint failed: Usuarios.mpps" in str(e):
                  return False, f"Error: El MPPS '{mpps}' ya está registrado para otro usuario."
             else:
                 return False, f"Error de base de datos al guardar: {e}"
        except Exception as e:
            print(f"MedicoActions General Error: {e}"); traceback.print_exc()
            # Rollback es automático con 'with conn:'
            return False, f"Error inesperado al guardar: {e}"
        finally:
            if conn: conn.close()

    def get_list(self):
        """ Obtiene la lista de TODOS los usuarios incluyendo los nuevos campos. """
        print("MedicoActions: Obteniendo lista de usuarios...")
        conn = None
        users = []
        try:
            conn = database.connect_db()
            cursor = conn.cursor()
            # Seleccionar todos los campos relevantes
            query = """
                SELECT 
                    id, nombre_usuario, nombre_completo, cedula, 
                    mpps, especialidad, ruta_foto_perfil, rol, activo, fecha_creacion 
                FROM Usuarios 
                ORDER BY id DESC
            """
            cursor.execute(query)
            rows = cursor.fetchall()
            colnames = [desc[0] for desc in cursor.description]
            cursor.close()
            print(f"MedicoActions: {len(rows)} usuarios encontrados. Desencriptando...")
            
            for row in rows:
                 user_dict = dict(zip(colnames, row))
                 try:
                     # Desencriptar campos necesarios
                     user_dict['nombre_completo_dec'] = database.decrypt_data(user_dict.get('nombre_completo'))
                     user_dict['cedula_dec'] = database.decrypt_data(user_dict.get('cedula'))
                     # Los demás campos (mpps, especialidad, ruta_foto_perfil, rol, activo, nombre_usuario) no están encriptados
                     
                 except Exception as e:
                     print(f"Warn: Error desencriptando datos para ID {user_dict.get('id', '??')}: {e}")
                     # Poner placeholders si falla la desencriptación
                     user_dict['nombre_completo_dec'] = user_dict.get('nombre_completo_dec', "[Error Desenc.]")
                     user_dict['cedula_dec'] = user_dict.get('cedula_dec', "[Error Desenc.]")
                     
                 # Formatear fecha para visualización (opcional, pero útil)
                 try:
                      if user_dict.get('fecha_creacion'):
                           dt_obj = datetime.fromisoformat(user_dict['fecha_creacion'])
                           user_dict['fecha_creacion_fmt'] = dt_obj.strftime('%d/%m/%Y %I:%M %p')
                      else:
                           user_dict['fecha_creacion_fmt'] = '-'
                 except ValueError:
                     user_dict['fecha_creacion_fmt'] = user_dict.get('fecha_creacion', '-') # Mostrar original si falla formato

                 users.append(user_dict)
                 
            return users, len(users) # Devuelve lista de diccionarios y conteo
            
        except Exception as e:
            print(f"Error en MedicoActions.get_list: {e}"); traceback.print_exc(); return None, 0
        finally:
            if conn: conn.close()

    # --- Funciones futuras ---
    def get_details(self, user_id):
         print(f"MedicoActions: Obteniendo detalles para usuario ID: {user_id}")
         conn = None
         user_details = None
         try:
             conn = database.connect_db()
             cursor = conn.cursor()
             query = """
                 SELECT 
                     id, nombre_usuario, nombre_completo, cedula, 
                     mpps, especialidad, ruta_foto_perfil, rol, activo, fecha_creacion 
                 FROM Usuarios 
                 WHERE id = ?
             """
             cursor.execute(query, (user_id,))
             row = cursor.fetchone()
             
             if row:
                 colnames = [desc[0] for desc in cursor.description]
                 raw_details = dict(zip(colnames, row)) # Datos crudos de la BD
                 
                 # Crear un nuevo diccionario SOLO con los datos procesados y serializables
                 processed_details = {}
                 processed_details['id'] = raw_details.get('id')
                 processed_details['nombre_usuario'] = raw_details.get('nombre_usuario')
                 processed_details['mpps'] = raw_details.get('mpps') # Ya es TEXT
                 processed_details['especialidad'] = raw_details.get('especialidad') # Ya es TEXT
                 processed_details['ruta_foto_perfil'] = raw_details.get('ruta_foto_perfil') # Ya es TEXT
                 processed_details['rol'] = raw_details.get('rol') # Ya es TEXT
                 processed_details['activo'] = raw_details.get('activo') # Ya es INTEGER (0 o 1)

                 # Desencriptar y añadir (resultado es string o None)
                 processed_details['nombre_completo_dec'] = database.decrypt_data(raw_details.get('nombre_completo'))
                 processed_details['cedula_dec'] = database.decrypt_data(raw_details.get('cedula'))

                 # Formatear fecha a string
                 fecha_creacion_str = raw_details.get('fecha_creacion')
                 processed_details['fecha_creacion_fmt'] = '-' # Default
                 if fecha_creacion_str:
                     try:
                          dt_obj = datetime.fromisoformat(fecha_creacion_str)
                          processed_details['fecha_creacion_fmt'] = dt_obj.strftime('%d/%m/%Y %I:%M %p')
                     except ValueError:
                          processed_details['fecha_creacion_fmt'] = fecha_creacion_str # Dejar como string original si falla

                 # NO incluir los campos BLOB originales ni objetos datetime
                 
                 user_details = processed_details # Asignar el diccionario procesado

                 print(f"MedicoActions: Detalles procesados para ID {user_id}: {list(user_details.keys())}")
             else:
                 print(f"MedicoActions: Usuario con ID {user_id} no encontrado.")
             
             cursor.close()
             # Devolver el diccionario con tipos seguros, o None si no se encontró usuario
             return user_details 

         except Exception as e:
             print(f"Error en MedicoActions.get_details: {e}"); traceback.print_exc(); return None
         finally:
             if conn: conn.close()

    def update_details(self, medico_id_to_update, medico_data, current_user_id):
        """
        Actualiza los detalles de un usuario existente, incluyendo la contraseña si se proporciona.
        Retorna: tuple (bool: success, str: message)
        """
        print(f"MedicoActions: Iniciando ACTUALIZAR usuario ID: {medico_id_to_update}")

        # Campos que se pueden actualizar desde el formulario
        nombre_completo = medico_data.get('nombre_completo')
        cedula = medico_data.get('cedula')
        mpps = medico_data.get('mpps')
        especialidad = medico_data.get('especialidad')
        ruta_foto_perfil = medico_data.get('ruta_foto_perfil') # ruta_foto_perfil puede ser actualizada si hay foto_base64
        nombre_usuario = medico_data.get('nombre_usuario')
        rol = medico_data.get('rol')
        activo = int(medico_data.get('activo', 1)) # Por defecto activo si no se envía

        # Obtener la nueva contraseña, si se proporcionó desde el frontend
        # El JS elimina 'contrasena' del objeto si el campo estaba vacío.
        nueva_contrasena = medico_data.get('contrasena')

        # --- Validaciones ---
        if not nombre_completo or not cedula or not nombre_usuario or not rol:
            return False, "Error: Nombre Completo, Cédula, Nombre de Usuario y Rol son requeridos."
        
        if not isinstance(cedula, str) or not (cedula.upper().startswith('V-') or cedula.upper().startswith('E-')) or not any(char.isdigit() for char in cedula.split('-')[-1]):
            return False, "Error: Formato de Cédula inválido (Ej: V-12345678 o E-12345678)."

        # Validación de contraseña (si se proporcionó una nueva)
        # El frontend ya valida longitud > 0 y < 4, pero una verificación aquí es buena.
        if nueva_contrasena and len(nueva_contrasena) < 4:
            return False, "Error: La nueva contraseña debe tener al menos 4 caracteres (o dejarse vacía para no cambiar)."

        conn = None
        try:
            conn = database.connect_db()
            with conn: # Transacción automática
                cursor = conn.cursor()

                # Encriptar datos sensibles que se van a actualizar
                nombre_completo_enc = database.encrypt_data(nombre_completo)
                cedula_enc = database.encrypt_data(cedula)

                # Construcción dinámica de la sentencia SET y los valores
                set_clauses = []
                values_for_update = []

                # Campos que siempre se intentan actualizar (el frontend los envía)
                set_clauses.extend([
                    "nombre_usuario = ?", "nombre_completo = ?", "cedula = ?",
                    "mpps = ?", "especialidad = ?", 
                    # ruta_foto_perfil se maneja si se sube una nueva foto, el frontend enviará la nueva ruta
                    "ruta_foto_perfil = ?", 
                    "rol = ?", "activo = ?"
                ])
                values_for_update.extend([
                    nombre_usuario.strip().lower(), nombre_completo_enc, cedula_enc,
                    mpps, especialidad, ruta_foto_perfil,
                    rol, activo
                ])

                # Si se proporcionó una nueva contraseña, añadirla al UPDATE
                if nueva_contrasena:
                    hashed_pw = hash_password(nueva_contrasena)
                    set_clauses.append("hash_contrasena = ?")
                    values_for_update.append(hashed_pw)
                    print(f"MedicoActions: Se actualizará la contraseña para el usuario ID: {medico_id_to_update}")
                else:
                    print(f"MedicoActions: No se proporcionó nueva contraseña. La contraseña del usuario ID: {medico_id_to_update} no se modificará.")

                sql = f"UPDATE Usuarios SET {', '.join(set_clauses)} WHERE id = ?"
                values_for_update.append(medico_id_to_update) # Añadir el ID del médico para el WHERE

                print(f"MedicoActions: Ejecutando UPDATE para usuario ID: {medico_id_to_update} con la query: {sql}")
                cursor.execute(sql, tuple(values_for_update))
                
                if cursor.rowcount == 0:
                    return False, f"Error: Usuario con ID {medico_id_to_update} no encontrado o datos sin cambios."

                print(f"MedicoActions: Usuario ID {medico_id_to_update} actualizado.")

                # Registrar Acción
                log_descripcion = f"Usuario ID {current_user_id} actualizó datos del usuario '{nombre_usuario}' (ID: {medico_id_to_update})."
                
                log_detalles = {'campos_enviados_para_actualizar': list(medico_data.keys())}
                if nueva_contrasena:
                    log_detalles['contrasena_modificada'] = True # Indicador explícito
                
                log_action(conn, current_user_id, 'ACTUALIZAR_USUARIO', log_descripcion,
                           tabla='Usuarios', registro_id=medico_id_to_update,
                           detalles=log_detalles)

            print("MedicoActions: Transacción de actualización completada.")
            return True, f"Datos del usuario '{nombre_usuario}' actualizados exitosamente."

        except sqlite3.IntegrityError as e:
            print(f"MedicoActions DB Integrity Error en UPDATE: {e}")
            if "UNIQUE constraint failed: Usuarios.nombre_usuario" in str(e):
                return False, f"Error: El nombre de usuario '{nombre_usuario}' ya existe. Por favor, elija otro."
            elif "UNIQUE constraint failed: Usuarios.cedula" in str(e):
                return False, f"Error: La cédula '{cedula}' ya está registrada para otro usuario."
            elif "UNIQUE constraint failed: Usuarios.mpps" in str(e):
                return False, f"Error: El MPPS '{mpps}' ya está registrado para otro usuario."
            else:
                return False, f"Error de base de datos al actualizar: {e}"
        except Exception as e:
            print(f"MedicoActions General Error en UPDATE: {e}"); traceback.print_exc()
            return False, f"Error inesperado al actualizar: {e}"
        finally:
            if conn: conn.close()

    def toggle_status(self, medico_id_to_toggle: int, current_user_id_actor: int):
        print(f"MedicoActions: Intentando cambiar estado para médico ID {medico_id_to_toggle} por usuario ID {current_user_id_actor}")
        conn = None
        try:
            # --- CORRECCIÓN AQUÍ ---
            conn = database.connect_db() # Usar el prefijo del módulo 'database'
            # -----------------------
            conn.row_factory = sqlite3.Row 
            cursor = conn.cursor()

            if medico_id_to_toggle == current_user_id_actor:
                 return False, "No puedes cambiar tu propio estado de activación.", -1

            cursor.execute("SELECT id, activo, nombre_usuario, nombre_completo FROM usuarios WHERE id = ?", (medico_id_to_toggle,))
            medico_actual = cursor.fetchone()

            if not medico_actual:
                return False, f"Usuario con ID {medico_id_to_toggle} no encontrado.", -1

            estado_actual = medico_actual['activo']
            nombre_usuario_afectado = medico_actual['nombre_usuario']
            
            nuevo_estado = 0 if estado_actual == 1 else 1

            cursor.execute("UPDATE usuarios SET activo = ? WHERE id = ?", (nuevo_estado, medico_id_to_toggle))
            
            accion_desc = "Activación" if nuevo_estado == 1 else "Desactivación"
            descripcion_log = f"{accion_desc} del usuario '{nombre_usuario_afectado}' (ID: {medico_id_to_toggle})."
            
            # --- CORRECCIÓN AQUÍ también para log_action ---
            database.log_action( # Usar el prefijo del módulo 'database'
                db_conn=conn,
                usuario_id=current_user_id_actor,
                tipo_accion="CAMBIO_ESTADO_USUARIO",
                descripcion=descripcion_log,
                tabla="usuarios",
                registro_id=medico_id_to_toggle,
                detalles={'nuevo_estado': nuevo_estado, 'estado_anterior': estado_actual}
            )
            # ----------------------------------------------
            
            conn.commit()
            mensaje_exito = f"Usuario '{nombre_usuario_afectado}' ha sido {'activado' if nuevo_estado == 1 else 'desactivado'} correctamente."
            print(f"MedicoActions: {mensaje_exito}")
            return True, mensaje_exito, nuevo_estado

        except sqlite3.Error as e_sql:
            if conn: conn.rollback()
            print(f"MedicoActions ERROR SQLite en toggle_status: {e_sql}")
            traceback.print_exc()
            return False, f"Error de base de datos al cambiar estado: {e_sql}", -1
        except Exception as e: # Captura NameError también si database no se importó
            if conn: conn.rollback()
            print(f"MedicoActions ERROR General en toggle_status: {e}")
            traceback.print_exc()
            # Devolver el mensaje de error específico para ayudar a depurar
            return False, f"Error inesperado al cambiar estado: {str(e)}", -1
        finally:
            if conn: conn.close()