# paciente_acciones.py
import sqlite3
import traceback
# Añadir json para la función de log
import json
# Asegurarse que date y datetime estén importados
from datetime import date, datetime
# Importar módulo database completo o funciones específicas
import database
# Importar función de log (asumiendo que está en database.py)
from database import log_action

class PatientActions:
    """
    Clase para encapsular las acciones relacionadas con los pacientes
    (Guardar, consultar, actualizar, etc.).
    """

    def __init__(self):
        # No necesita inicialización especial por ahora
        pass

    def _get_next_patient_id(self, cursor):
        """Obtiene el próximo ID potencial para un paciente."""
        cursor.execute("SELECT MAX(id) FROM Pacientes")
        max_id_tuple = cursor.fetchone()
        max_id = max_id_tuple[0] if max_id_tuple and max_id_tuple[0] is not None else 0
        next_id = max_id + 1
        # Quitar print redundante si se quiere
        # print(f"PatientActions: Próximo ID de paciente estimado: {next_id}")
        return next_id

    def _format_historia_numero(self, patient_id):
        """Formatea el ID del paciente como N° Historia (Ej: H-000001)."""
        return f"H-{patient_id:06d}"

    def get_next_historia(self):
        """Obtiene y formatea el próximo N° de Historia potencial."""
        print("PatientActions: Obteniendo próximo N° Historia...")
        conn = None
        next_historia = "(Error)" # Valor por defecto en caso de fallo
        try:
            conn = database.connect_db()
            if conn:
                cursor = conn.cursor()
                next_id = self._get_next_patient_id(cursor)
                next_historia = self._format_historia_numero(next_id)
                cursor.close()
                print(f"PatientActions: Próximo N° Historia estimado: {next_historia}")
            else:
                print("PatientActions Error: No se pudo conectar a BD.")
                next_historia = "(Error DB)"
        except Exception as e:
            print(f"PatientActions Error: Error obteniendo próximo N° Historia: {e}")
            traceback.print_exc()
            next_historia = "(Error Calc)"
        finally:
            if conn: conn.close()
        return next_historia

    def save_new(self, patient_data, current_user_id):
        """
        Guarda un nuevo paciente. Obtiene el ID, genera N° Historia, e inserta todo.
        Registra la acción en el historial.
        Retorna: tuple (bool: success, str: message, str: new_historia_numero o None si falla)
        """
        print("PatientActions: Iniciando guardado de nuevo paciente...")

        # Validaciones
        if not patient_data.get('nombres') or not patient_data.get('apellidos'):
            return False, "Error: Nombres y Apellidos son requeridos.", None
        if not current_user_id:
            return False, "Error: ID de usuario no proporcionado.", None

        conn = None
        assigned_id = 0 # ID real asignado por la BD
        generated_historia = None

        try:
            conn = database.connect_db()
            if not conn: raise sqlite3.Error("No se pudo conectar a la base de datos.")

            conn.execute("BEGIN TRANSACTION;")
            cursor = conn.cursor()
            print("PatientActions: Transacción iniciada.")

            # Obtener próximo ID y generar N° Historia
            next_id_estimated = self._get_next_patient_id(cursor)
            generated_historia = self._format_historia_numero(next_id_estimated)
            print(f"PatientActions: N° Historia generado: {generated_historia} para ID potencial: {next_id_estimated}")

            # --- 1. Insertar en Pacientes ---
            print("PatientActions: Preparando datos para Pacientes...")
            paciente_sql_data = {
                "numero_historia": generated_historia,
                "usuario_registro_id": current_user_id, # Guardar quién lo registró
                "cedula": database.encrypt_data(patient_data.get('cedula')),
                "nombres": database.encrypt_data(patient_data['nombres']),
                "apellidos": database.encrypt_data(patient_data['apellidos']),
                "sexo": patient_data.get('sexo'),
                "fecha_nacimiento": patient_data.get('fecha_nacimiento') or None,
                "lugar_nacimiento": database.encrypt_data(patient_data.get('lugar_nacimiento')),
                "estado_civil": database.encrypt_data(patient_data.get('estado_civil')),
                "telefono_habitacion": database.encrypt_data(patient_data.get('telefono_habitacion')),
                "telefono_movil": database.encrypt_data(patient_data.get('telefono_movil')),
                "email": database.encrypt_data(patient_data.get('email')),
                "direccion": database.encrypt_data(patient_data.get('direccion')),
                "profesion_oficio": database.encrypt_data(patient_data.get('profesion_oficio')),
                "emerg_telefono": database.encrypt_data(patient_data.get('emerg_telefono')),
                "emerg_parentesco": database.encrypt_data(patient_data.get('emerg_parentesco')),
                "emerg_direccion": database.encrypt_data(patient_data.get('emerg_direccion')),
                "notas_adicionales": database.encrypt_data(patient_data.get('notas_adicionales')), # Añadir si existe en form
                "ap_asma": 1 if patient_data.get('ap_asma') else 0,
                "ap_hta": 1 if patient_data.get('ap_hta') else 0,
                "ap_dm": 1 if patient_data.get('ap_dm') else 0,
                "ap_otros": 1 if patient_data.get('ap_otros') else 0,
                "ap_asma_detalle": database.encrypt_data(patient_data.get('ap_asma_detalle')),
                "ap_hta_detalle": database.encrypt_data(patient_data.get('ap_hta_detalle')),
                "ap_dm_detalle": database.encrypt_data(patient_data.get('ap_dm_detalle')),
                "ap_otros_detalle": database.encrypt_data(patient_data.get('ap_otros_detalle')),
                "ap_alergias": database.encrypt_data(patient_data.get('ap_alergias')),
                "ap_quirurgicos": database.encrypt_data(patient_data.get('ap_quirurgicos')),
                "af_madre": database.encrypt_data(patient_data.get('af_madre')),
                "af_padre": database.encrypt_data(patient_data.get('af_padre')),
                "af_hermanos": database.encrypt_data(patient_data.get('af_hermanos')),
                "af_hijos": database.encrypt_data(patient_data.get('af_hijos')),
                "hab_tabaco": database.encrypt_data(patient_data.get('hab_tabaco')),
                "hab_alcohol": database.encrypt_data(patient_data.get('hab_alcohol')),
                "hab_drogas": database.encrypt_data(patient_data.get('hab_drogas')),
                "hab_cafe": database.encrypt_data(patient_data.get('hab_cafe')),
                # fecha_registro, fecha_ultima_mod, usuario_ultima_mod_id se manejan con DEFAULT o UPDATEs
            }
            paciente_cols = ", ".join(paciente_sql_data.keys())
            paciente_placeholders = ", ".join(["?"] * len(paciente_sql_data))
            paciente_sql = f"INSERT INTO Pacientes ({paciente_cols}) VALUES ({paciente_placeholders})"
            paciente_values = tuple(paciente_sql_data.values())

            print(f"PatientActions: Ejecutando SQL INSERT Pacientes...")
            cursor.execute(paciente_sql, paciente_values)
            assigned_id = cursor.lastrowid
            print(f"PatientActions: Paciente insertado con ID real: {assigned_id}")

            # --- 2. Insertar en Consultas ---
            print("PatientActions: Preparando datos para Consultas...")
            consulta_sql_data = {
                "paciente_id": assigned_id,
                "usuario_id": current_user_id,
                "motivo_consulta": database.encrypt_data(patient_data.get('motivo_consulta')),
                "historia_enfermedad_actual": database.encrypt_data(patient_data.get('historia_enfermedad_actual')),
                "diagnostico_ingreso": database.encrypt_data(patient_data.get('diagnostico_ingreso')),
            }
            consulta_cols = ", ".join(consulta_sql_data.keys())
            consulta_placeholders = ", ".join(["?"] * len(consulta_sql_data))
            consulta_sql = f"INSERT INTO Consultas ({consulta_cols}) VALUES ({consulta_placeholders})"
            consulta_values = tuple(consulta_sql_data.values())
            cursor.execute(consulta_sql, consulta_values); new_consulta_id = cursor.lastrowid
            print(f"PatientActions: Consulta insertada ID: {new_consulta_id}")

            # --- 3. Insertar en ExamenesFisicos ---
            print("PatientActions: Preparando datos para ExamenesFisicos...")
            examen_sql_data = {
                "consulta_id": new_consulta_id,
                "ef_ta": database.encrypt_data(patient_data.get('ef_ta')), "ef_fr": patient_data.get('ef_fr') or None,
                "ef_fc": patient_data.get('ef_fc') or None, "ef_sato2": patient_data.get('ef_sato2') or None,
                "ef_temp": database.encrypt_data(patient_data.get('ef_temp')), "ef_glic": patient_data.get('ef_glic') or None,
                "ef_piel": database.encrypt_data(patient_data.get('ef_piel')), "ef_respiratorio": database.encrypt_data(patient_data.get('ef_respiratorio')),
                "ef_cardiovascular": database.encrypt_data(patient_data.get('ef_cardiovascular')), "ef_abdomen": database.encrypt_data(patient_data.get('ef_abdomen')),
                "ef_gastrointestinal": database.encrypt_data(patient_data.get('ef_gastrointestinal')), "ef_genitourinario": database.encrypt_data(patient_data.get('ef_genitourinario')),
                "ef_extremidades": database.encrypt_data(patient_data.get('ef_extremidades')), "ef_neurologico": database.encrypt_data(patient_data.get('ef_neurologico')),
                "ef_otros_hallazgos": database.encrypt_data(patient_data.get('ef_otros_hallazgos')),
            }
            examen_cols = ", ".join(examen_sql_data.keys()); examen_placeholders = ", ".join(["?"] * len(examen_sql_data))
            examen_sql = f"INSERT INTO ExamenesFisicos ({examen_cols}) VALUES ({examen_placeholders})"
            examen_values = tuple(examen_sql_data.values()); cursor.execute(examen_sql, examen_values)
            print("PatientActions: Examen Físico insertado.")

            # --- 4. Registrar Acción en Historial ---
            log_descripcion = f"Creó paciente '{generated_historia}' ({patient_data.get('nombres','')} {patient_data.get('apellidos','')}). Consulta inicial ID: {new_consulta_id}."
            # No incluir patient_data directamente en detalles por seguridad/tamaño, quizás solo IDs o resumen
            log_action(conn, current_user_id, 'CREAR_PACIENTE', log_descripcion,
                       tabla='Pacientes', registro_id=assigned_id)

            # Commit
            conn.commit()
            print("PatientActions: Transacción completada exitosamente.")
            return True, f"Paciente registrado con N° Historia: {generated_historia}", generated_historia

        except sqlite3.Error as db_err:
            print(f"PatientActions DB Error: {db_err}"); traceback.print_exc()
            if conn: conn.rollback()
            return False, f"Error de base de datos: {db_err}", None
        except Exception as e:
            print(f"PatientActions General Error: {e}"); traceback.print_exc()
            if conn: conn.rollback()
            return False, f"Error inesperado: {e}", None
        finally:
            if conn: conn.close()

    def calculate_age(self, dob_str):
        if not dob_str: return None
        try:
            dob = date.fromisoformat(dob_str)
            today = date.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            return age
        except (ValueError, TypeError): return None

    def get_list(self, search_term=None):
        print(f"PatientActions: get_list REAL (search: '{search_term}')")
        conn = None
        patients = []
        total_count = 0
        select_fields = "id, numero_historia, nombres, apellidos, cedula, fecha_nacimiento, sexo"
        base_query = f"SELECT {select_fields} FROM Pacientes"
        count_query = "SELECT COUNT(id) FROM Pacientes"
        params = []
        where_clauses = []

        if search_term:
            search_like = f"%{search_term}%"
            where_clauses.append("numero_historia LIKE ?")
            params.append(search_like)

        if where_clauses:
            sql_where = " WHERE " + " AND ".join(where_clauses)
            base_query += sql_where
            count_query += sql_where

        base_query += " ORDER BY id DESC"

        try:
            conn = database.connect_db()
            if not conn: raise sqlite3.Error("Fallo conexión DB")
            cursor = conn.cursor()

            cursor.execute(count_query, params)
            total_count = cursor.fetchone()[0]

            cursor.execute(base_query, params)
            rows = cursor.fetchall()
            colnames = [desc[0] for desc in cursor.description]
            cursor.close() # Cerrar cursor aquí

            for row in rows:
                patient_dict = dict(zip(colnames, row))
                try:
                    nombres_dec = database.decrypt_data(patient_dict.get('nombres')) or ''
                    apellidos_dec = database.decrypt_data(patient_dict.get('apellidos')) or ''
                    patient_dict['nombre_completo'] = f"{nombres_dec} {apellidos_dec}".strip()
                    patient_dict['cedula'] = database.decrypt_data(patient_dict.get('cedula'))
                    patient_dict['edad'] = self.calculate_age(patient_dict.get('fecha_nacimiento'))
                except Exception as decrypt_error:
                     print(f"Warn: Error procesando ID {patient_dict.get('id')}: {decrypt_error}")
                     patient_dict['nombre_completo'] = "[Error]"
                     patient_dict['cedula'] = "[Error]"
                     patient_dict['edad'] = '??'
                patients.append(patient_dict)

            print(f"PatientActions: Devolviendo {len(patients)} pacientes filtrados.")
            return patients, total_count # Devolver total_count original para posible paginación futura

        except sqlite3.Error as db_err:
            print(f"DB Error get_list: {db_err}"); traceback.print_exc(); return None, 0
        except Exception as e:
            print(f"Error get_list: {e}"); traceback.print_exc(); return None, 0
        finally:
            if conn: conn.close()

    def get_details(self, patient_id):
        print(f"PatientActions: Obteniendo TODOS los detalles para paciente ID: {patient_id}")
        conn = None
        patient_details = { # Diccionario principal a devolver
            "info": None,
            "consultas_info": [], # Lista con info básica de cada consulta
            "evoluciones_todas": [],
            "ordenes_medicas_todas": [],
            "complementarios_todos": [],
            "interconsultas_todas": [],
            "informes_medicos_todos": [],
            "recipes_todos": [],
            "examen_fisico_inicial": None # Para la pestaña Resumen Ingreso
        }

        try:
            conn = database.connect_db()
            if not conn: raise sqlite3.Error("Fallo conexión DB")
            cursor = conn.cursor()

            # --- 1. Obtener Datos del Paciente (Como antes, pero simplificado) ---
            print("PatientActions: Obteniendo datos básicos del paciente...")
            cursor.execute("SELECT * FROM Pacientes WHERE id = ?", (patient_id,))
            patient_row = cursor.fetchone()
            if not patient_row:
                print(f"PatientActions Error: Paciente ID {patient_id} no encontrado."); return None # Retorna None si no existe

            patient_cols = [desc[0] for desc in cursor.description]
            patient_info_raw = dict(zip(patient_cols, patient_row))
            patient_info_processed = {'id': patient_info_raw['id']}
            for key, value in patient_info_raw.items():
                if key == 'id': continue
                excluded_keys = ['fecha_nacimiento', 'fecha_registro', 'sexo', 'numero_historia',
                                 'ap_asma', 'ap_hta', 'ap_dm', 'ap_otros', # Estos son flags 0/1
                                 'usuario_registro_id', 'fecha_ultima_mod', 'usuario_ultima_mod_id']
                if isinstance(value, bytes) and key not in excluded_keys:
                    try: patient_info_processed[key] = database.decrypt_data(value)
                    except Exception as e: patient_info_processed[key] = "[Error Decrypt]"
                else: patient_info_processed[key] = value # Copiar flags y no-blobs

            # Añadir campos de flags explícitos si no existen (por si acaso)
            patient_info_processed['ap_asma'] = patient_info_raw.get('ap_asma', 0)
            patient_info_processed['ap_hta'] = patient_info_raw.get('ap_hta', 0)
            patient_info_processed['ap_dm'] = patient_info_raw.get('ap_dm', 0)
            patient_info_processed['ap_otros'] = patient_info_raw.get('ap_otros', 0)


            if patient_info_processed.get('fecha_nacimiento'):
                patient_info_processed['edad_calculada'] = self.calculate_age(patient_info_processed['fecha_nacimiento'])

            patient_details['info'] = patient_info_processed # Asignar datos del paciente

            print("PatientActions: Obteniendo info básica de consultas...")
            cursor.execute("""
                SELECT c.id, c.paciente_id, c.usuario_id, c.fecha_hora_ingreso, c.fecha_hora_egreso,
                       c.usuario_cierre_id, c.motivo_consulta, c.historia_enfermedad_actual, c.diagnostico_ingreso,
                       COALESCE(u_inicio.nombre_completo, u_inicio.nombre_usuario) as usuario_inicio_nombre, 
                       COALESCE(u_cierre.nombre_completo, u_cierre.nombre_usuario) as usuario_cierre_nombre
                FROM Consultas c
                LEFT JOIN Usuarios u_inicio ON c.usuario_id = u_inicio.id
                LEFT JOIN Usuarios u_cierre ON c.usuario_cierre_id = u_cierre.id
                WHERE c.paciente_id = ? ORDER BY c.fecha_hora_ingreso DESC
            """, (patient_id,))
            consulta_rows = cursor.fetchall()
            consulta_cols = [desc[0] for desc in cursor.description]
            initial_consultation_id = None 

            for i, consulta_row in enumerate(consulta_rows):
                consulta_info_raw = dict(zip(consulta_cols, consulta_row))
                consulta_id = consulta_info_raw['id'] # <--- Obtienes el ID de la consulta

                if i == 0: 
                    initial_consultation_id = consulta_id # Guardas el ID de la primera (más reciente)

                # Creas el diccionario procesado INCLUYENDO el 'id'
                consulta_info_processed = {'id': consulta_id, 'paciente_id': consulta_info_raw['paciente_id']} 
                
                for key, value in consulta_info_raw.items():
                    if key in ['id', 'paciente_id']: continue 

                    excluded_keys_consulta = ['usuario_id', 'usuario_cierre_id', 'fecha_hora_ingreso', 'fecha_hora_egreso']

                    # Si nombre_completo de Usuarios es BLOB, necesitas desencriptarlo aquí también.
                    # La consulta SQL ya intenta con COALESCE, pero si el nombre_completo es un BLOB, 
                    # el COALESCE devolverá el BLOB o el nombre_usuario (texto).
                    # Necesitas manejar la desencriptación del nombre_completo si es BLOB.

                    if key in ['usuario_inicio_nombre', 'usuario_cierre_nombre']:
                        # Si estos campos pueden ser BLOB (porque nombre_completo en Usuarios es BLOB)
                        if isinstance(value, bytes):
                            try:
                                consulta_info_processed[key] = database.decrypt_data(value)
                            except Exception:
                                consulta_info_processed[key] = "[Error Decrypt Nombre]"
                        else: # Es texto (probablemente el nombre_usuario del COALESCE)
                            consulta_info_processed[key] = value
                    elif isinstance(value, bytes) and key not in excluded_keys_consulta:
                        try:
                            consulta_info_processed[key] = database.decrypt_data(value)
                        except Exception:
                            consulta_info_processed[key] = "[Error Decrypt]"
                    elif key not in excluded_keys_consulta:
                        consulta_info_processed[key] = value
                
                patient_details['consultas_info'].append(consulta_info_processed) # <<<--- AQUÍ SE AÑADE A LA LISTA


            # --- 3. Obtener Examen Físico INICIAL (si existe) ---
            if initial_consultation_id:
                print(f"PatientActions: Obteniendo examen físico inicial (Consulta ID: {initial_consultation_id})...")
                cursor.execute("SELECT * FROM ExamenesFisicos WHERE consulta_id = ?", (initial_consultation_id,))
                examen_row = cursor.fetchone()
                if examen_row:
                    examen_cols = [d[0] for d in cursor.description]
                    examen_info_raw = dict(zip(examen_cols, examen_row))
                    ef_inicial_proc = {'id': examen_info_raw['id']}
                    for key, value in examen_info_raw.items():
                        if key in ['id', 'consulta_id']: continue
                        excluded_keys_ef = ['fecha_hora', 'ef_fr', 'ef_fc', 'ef_sato2', 'ef_glic']
                        if isinstance(value, bytes) and key not in excluded_keys_ef:
                            try: ef_inicial_proc[key] = database.decrypt_data(value)
                            except Exception: ef_inicial_proc[key] = "[Error Decrypt]"
                        else: ef_inicial_proc[key] = value
                    patient_details['examen_fisico_inicial'] = ef_inicial_proc

            # --- 4. Obtener TODAS las Evoluciones del Paciente ---
            print("PatientActions: Obteniendo todas las evoluciones...")
            cursor.execute("""
                SELECT e.*, 
                       u_creador.nombre_usuario as u_creador_username,
                       u_creador.nombre_completo as u_creador_fullname_enc,
                       u_mod.nombre_usuario as u_mod_username,
                       u_mod.nombre_completo as u_mod_fullname_enc
                FROM Evoluciones e
                JOIN Consultas c ON e.consulta_id = c.id
                JOIN Usuarios u_creador ON e.usuario_id = u_creador.id
                LEFT JOIN Usuarios u_mod ON e.usuario_ultima_mod_id = u_mod.id
                WHERE c.paciente_id = ?
                ORDER BY e.fecha_hora DESC
            """, (patient_id,))
            evo_rows = cursor.fetchall()
            evo_cols = [d[0] for d in cursor.description]
            for evo_row in evo_rows:
                evo_info_raw = dict(zip(evo_cols, evo_row))
                evo_info_processed = {'id': evo_info_raw['id']}

                # Desencriptar nombre_completo para creador
                creador_fullname_dec = None
                if evo_info_raw.get('u_creador_fullname_enc'):
                    try:
                        creador_fullname_dec = database.decrypt_data(evo_info_raw['u_creador_fullname_enc'])
                    except Exception:
                        creador_fullname_dec = "[Err Fullname]"
                evo_info_processed['usuario_creador_nombre_completo'] = creador_fullname_dec or evo_info_raw.get('u_creador_username') or "N/D"
                # Mantener username por si se usa como fallback o para logs internos
                evo_info_processed['usuario_creador_username'] = evo_info_raw.get('u_creador_username') 


                # Desencriptar nombre_completo para modificador
                mod_fullname_dec = None
                if evo_info_raw.get('u_mod_fullname_enc'):
                    try:
                        mod_fullname_dec = database.decrypt_data(evo_info_raw['u_mod_fullname_enc'])
                    except Exception:
                        mod_fullname_dec = "[Err Fullname]"
                evo_info_processed['usuario_modificador_nombre_completo'] = mod_fullname_dec or evo_info_raw.get('u_mod_username') or "N/D"
                evo_info_processed['usuario_modificador_username'] = evo_info_raw.get('u_mod_username')


                # Procesar otros campos de la evolución
                for key, value in evo_info_raw.items():
                    if key in ['id', 'u_creador_username', 'u_creador_fullname_enc', 'u_mod_username', 'u_mod_fullname_enc']: continue
                    
                    blob_fields_evo = ['ev_subjetivo', 'ev_objetivo', 'ev_ta', 'ev_temp', 'ev_piel', 'ev_respiratorio', 'ev_cardiovascular', 'ev_abdomen', 'ev_extremidades', 'ev_neurologico', 'ev_otros', 'ev_diagnosticos', 'ev_tratamiento_plan', 'ev_comentario']
                    excluded_keys_evo = ['consulta_id', 'usuario_id', 'fecha_hora', 'dias_hospitalizacion', 'ev_fc', 'ev_fr', 'ev_sato2', 'fecha_ultima_mod', 'usuario_ultima_mod_id']

                    if key in blob_fields_evo and isinstance(value, bytes):
                        try: evo_info_processed[key] = database.decrypt_data(value)
                        except Exception: evo_info_processed[key] = "[Error Decrypt]"
                    elif key not in excluded_keys_evo:
                        evo_info_processed[key] = value
                    elif key in ['fecha_hora', 'fecha_ultima_mod']: # Copiar fechas importantes
                        evo_info_processed[key] = value
                
                patient_details['evoluciones_todas'].append(evo_info_processed)


            # --- 5. Obtener TODAS las Órdenes Médicas ---
            # --- 5. Obtener TODAS las Órdenes Médicas ---
            print("PatientActions: Obteniendo todas las órdenes médicas...")
            cursor.execute("""
                SELECT om.id, om.consulta_id, om.evolucion_id, om.usuario_id, om.fecha_hora, 
                       om.orden_json_blob, om.estado,
                       COALESCE(u.nombre_completo, u.nombre_usuario) as usuario_orden_nombre_enc
                FROM OrdenesMedicas om
                JOIN Usuarios u ON om.usuario_id = u.id
                JOIN Consultas c ON om.consulta_id = c.id -- Asegurar que la consulta pertenezca al paciente
                WHERE c.paciente_id = ? 
                ORDER BY om.fecha_hora DESC
            """, (patient_id,)) # Filtrar por patient_id a través de la consulta
            om_rows = cursor.fetchall()
            om_cols = [d[0] for d in cursor.description]
            
            for om_row in om_rows:
                om_info_raw = dict(zip(om_cols, om_row))
                om_info_proc = {'id': om_info_raw['id']}

                # Procesar campos no blob o que no son el json principal
                for key, value in om_info_raw.items():
                    if key in ['id', 'orden_json_blob', 'usuario_orden_nombre_enc']: # Excluir estos por ahora
                        continue
                    om_info_proc[key] = value

                # Desencriptar nombre del usuario que ordenó
                nombre_usuario_enc = om_info_raw.get('usuario_orden_nombre_enc')
                if nombre_usuario_enc and isinstance(nombre_usuario_enc, bytes):
                    try:
                        om_info_proc['usuario_orden_nombre'] = database.decrypt_data(nombre_usuario_enc)
                    except:
                        om_info_proc['usuario_orden_nombre'] = "[Error Decrypt Nombre]"
                elif nombre_usuario_enc: # Ya es texto
                    om_info_proc['usuario_orden_nombre'] = nombre_usuario_enc
                else:
                    om_info_proc['usuario_orden_nombre'] = "N/D"


                # ---- PROCESAMIENTO DE orden_json_blob ----
                blob_original = om_info_raw.get('orden_json_blob')
                if blob_original and isinstance(blob_original, bytes):
                    try:
                        decrypted_json_string = database.decrypt_data(blob_original)
                        # El resultado de decrypt_data DEBE SER un string JSON
                        om_info_proc['orden_json_blob'] = decrypted_json_string if decrypted_json_string else "{}"
                        # Log para verificar
                        print(f"   Orden ID {om_info_proc['id']}: orden_json_blob desencriptado a string: '{str(om_info_proc['orden_json_blob'])[:100]}...'")
                    except Exception as e_decrypt_om:
                        print(f"   ERROR desencriptando orden_json_blob para orden ID {om_info_proc['id']}: {e_decrypt_om}")
                        om_info_proc['orden_json_blob'] = json.dumps({"error_desencriptacion": f"Fallo al desencriptar blob: {str(e_decrypt_om)}"})
                elif blob_original: # Si no es bytes pero existe (ej. ya es un string, aunque no debería ser si viene de la BD)
                    print(f"   WARN: orden_json_blob para orden ID {om_info_proc['id']} no era bytes, sino {type(blob_original)}. Usando tal cual.")
                    om_info_proc['orden_json_blob'] = str(blob_original) # Asegurar que sea string
                else: # Si es None o vacío
                    print(f"   Orden ID {om_info_proc['id']}: orden_json_blob es None o vacío. Se usará '{{}}'.")
                    om_info_proc['orden_json_blob'] = "{}" # String de JSON vacío
                # ---- FIN PROCESAMIENTO DE orden_json_blob ----
                
                patient_details['ordenes_medicas_todas'].append(om_info_proc)


            # --- 6. Obtener TODOS los Complementarios ---
            print("PatientActions: Obteniendo todos los complementarios...")
            cursor.execute("""
                SELECT comp.*, u.nombre_usuario as usuario_registrador_nombre
                FROM Complementarios comp
                LEFT JOIN Usuarios u ON comp.usuario_registrador_id = u.id
                WHERE comp.paciente_id = ?
                ORDER BY comp.fecha_registro DESC
            """, (patient_id,))
            comp_rows = cursor.fetchall()
            comp_cols = [d[0] for d in cursor.description]
            for comp_row in comp_rows:
                comp_info_raw = dict(zip(comp_cols, comp_row))
                comp_info_proc = {'id': comp_info_raw['id']}
                blob_fields_comp = ['nombre_estudio', 'resultado_informe', 'archivo_adjunto_path']
                excluded_keys_comp = ['id', 'paciente_id', 'consulta_id', 'orden_medica_id', 'usuario_registrador_id', 'fecha_registro', 'tipo_complementario', 'fecha_realizacion', 'usuario_registrador_nombre']
                for key, value in comp_info_raw.items():
                     if key in blob_fields_comp and isinstance(value, bytes):
                         try: comp_info_proc[key] = database.decrypt_data(value)
                         except Exception: comp_info_proc[key] = "[Error Decrypt]"
                     elif key not in excluded_keys_comp: comp_info_proc[key] = value
                     elif key in ['usuario_registrador_nombre', 'fecha_registro', 'fecha_realizacion', 'tipo_complementario']: comp_info_proc[key] = value # Copiar campos importantes
                patient_details['complementarios_todos'].append(comp_info_proc)

            # --- 7. Obtener TODAS las Interconsultas ---
            print("PatientActions: Obteniendo todas las interconsultas...")
            cursor.execute("""
                 SELECT ic.*, u_sol.nombre_usuario as usuario_solicitante_nombre,
                        u_resp.nombre_usuario as usuario_respuesta_nombre
                 FROM Interconsultas ic
                 JOIN Usuarios u_sol ON ic.usuario_solicitante_id = u_sol.id
                 LEFT JOIN Usuarios u_resp ON ic.usuario_respuesta_id = u_resp.id
                 WHERE ic.paciente_id = ?
                 ORDER BY ic.fecha_solicitud DESC
            """, (patient_id,))
            ic_rows = cursor.fetchall()
            ic_cols = [d[0] for d in cursor.description]
            for ic_row in ic_rows:
                ic_info_raw = dict(zip(ic_cols, ic_row))
                ic_info_proc = {'id': ic_info_raw['id']}
                blob_fields_ic = ['servicio_consultado', 'motivo_consulta', 'respuesta_texto']
                excluded_keys_ic = ['id', 'paciente_id', 'consulta_id', 'orden_medica_id', 'usuario_solicitante_id', 'fecha_solicitud', 'fecha_respuesta', 'usuario_respuesta_id', 'estado', 'usuario_solicitante_nombre', 'usuario_respuesta_nombre']
                for key, value in ic_info_raw.items():
                    if key in blob_fields_ic and isinstance(value, bytes):
                         try: ic_info_proc[key] = database.decrypt_data(value)
                         except Exception: ic_info_proc[key] = "[Error Decrypt]"
                    elif key not in excluded_keys_ic: ic_info_proc[key] = value
                    elif key in ['usuario_solicitante_nombre', 'usuario_respuesta_nombre', 'fecha_solicitud', 'fecha_respuesta', 'estado']: ic_info_proc[key] = value # Copiar
                patient_details['interconsultas_todas'].append(ic_info_proc)


            # --- 8. Obtener TODOS los Informes Médicos ---
            print("PatientActions: Obteniendo todos los informes médicos...")
            cursor.execute("""
                 SELECT im.*, u.nombre_usuario as usuario_creador_nombre
                 FROM InformesMedicos im
                 JOIN Usuarios u ON im.usuario_id = u.id
                 WHERE im.paciente_id = ?
                 ORDER BY im.fecha_creacion DESC
            """, (patient_id,))
            im_rows = cursor.fetchall()
            im_cols = [d[0] for d in cursor.description]
            for im_row in im_rows:
                im_info_raw = dict(zip(im_cols, im_row))
                im_info_proc = {'id': im_info_raw['id']}
                blob_fields_im = ['contenido_texto', 'archivo_generado_path']
                excluded_keys_im = ['id', 'paciente_id', 'consulta_id', 'usuario_id', 'fecha_creacion', 'tipo_informe', 'usuario_creador_nombre']
                for key, value in im_info_raw.items():
                     if key in blob_fields_im and isinstance(value, bytes):
                         try: im_info_proc[key] = database.decrypt_data(value)
                         except Exception: im_info_proc[key] = "[Error Decrypt]"
                     elif key not in excluded_keys_im: im_info_proc[key] = value
                     elif key in ['usuario_creador_nombre', 'fecha_creacion', 'tipo_informe']: im_info_proc[key] = value # Copiar
                patient_details['informes_medicos_todos'].append(im_info_proc)


            # --- 9. Obtener TODOS los Recipes ---
            print("PatientActions: Obteniendo todos los récipes...")
            cursor.execute("""
                 SELECT r.*, u.nombre_usuario as usuario_emisor_nombre
                 FROM Recipes r
                 JOIN Usuarios u ON r.usuario_id = u.id
                 WHERE r.paciente_id = ?
                 ORDER BY r.fecha_emision DESC
            """, (patient_id,))
            r_rows = cursor.fetchall()
            r_cols = [d[0] for d in cursor.description]
            for r_row in r_rows:
                r_info_raw = dict(zip(r_cols, r_row))
                r_info_proc = {'id': r_info_raw['id']}
                blob_fields_r = ['recipe_texto']
                excluded_keys_r = ['id', 'paciente_id', 'consulta_id', 'evolucion_id', 'usuario_id', 'fecha_emision', 'tipo', 'usuario_emisor_nombre']
                for key, value in r_info_raw.items():
                     if key in blob_fields_r and isinstance(value, bytes):
                          try: r_info_proc[key] = database.decrypt_data(value)
                          except Exception: r_info_proc[key] = "[Error Decrypt]"
                     elif key not in excluded_keys_r: r_info_proc[key] = value
                     elif key in ['usuario_emisor_nombre', 'fecha_emision', 'tipo']: r_info_proc[key] = value # Copiar
                patient_details['recipes_todos'].append(r_info_proc)


            cursor.close()
            print(f"PatientActions: Detalles completos recuperados para ID: {patient_id}. Estructura lista para pestañas.")
            return patient_details # Devolver el diccionario completo

        except sqlite3.Error as db_err:
            print(f"DB Error get_details: {db_err}"); traceback.print_exc(); return None
        except Exception as e:
            print(f"Error get_details: {e}"); traceback.print_exc(); return None
        finally:
            if conn: conn.close()

    def update_basic_data(self, patient_data: dict, current_user_id: int):
        """
        Actualiza los datos básicos (demográficos, contacto, emergencia, notas) de un paciente.
        Retorna: tuple (bool: success, str: message)
        """
        # --- OBTENER Y CONVERTIR ID ---
        patient_id_str = patient_data.get('id') # Obtener como viene (probablemente string)
        patient_id = None
        if patient_id_str:
            try:
                patient_id = int(patient_id_str) # Intentar convertir a entero
            except (ValueError, TypeError):
                print(f"PacienteActions WARN: No se pudo convertir el ID '{patient_id_str}' a entero.")
                # Devolver error inmediatamente si no se puede convertir
                return False, f"Error: ID de paciente '{patient_id_str}' no es válido."
        
        print(f"PacienteActions: Iniciando actualización datos básicos para Paciente ID: {patient_id} (Tipo: {type(patient_id)})")

        # --- VALIDACIÓN (ahora con patient_id como entero o None) ---
        if not patient_id or not isinstance(patient_id, int) or patient_id <= 0:
             # Este error ahora solo debería ocurrir si el ID era vacío, 0, negativo, o falló la conversión inicial.
             return False, f"Error: ID de paciente inválido ({patient_id})."
        # --- FIN VALIDACIÓN ---

        # --- Extraer y Validar otros Datos del Diccionario ---
        # ... (extraer nombres, apellidos, cedula, etc. como antes) ...
        nombres = patient_data.get('nombres')
        apellidos = patient_data.get('apellidos')
        cedula = patient_data.get('cedula')
        fecha_nacimiento = patient_data.get('fecha_nacimiento')
        sexo = patient_data.get('sexo')
        lugar_nacimiento = patient_data.get('lugar_nacimiento')
        estado_civil = patient_data.get('estado_civil')
        profesion_oficio = patient_data.get('profesion_oficio')
        telefono_habitacion = patient_data.get('telefono_habitacion')
        telefono_movil = patient_data.get('telefono_movil')
        email = patient_data.get('email')
        direccion = patient_data.get('direccion')
        emerg_nombre = patient_data.get('emerg_nombre')
        emerg_parentesco = patient_data.get('emerg_parentesco')
        emerg_telefono = patient_data.get('emerg_telefono')
        emerg_direccion = patient_data.get('emerg_direccion')
        notas_adicionales = patient_data.get('notas_adicionales')
        
        if not nombres or not apellidos or not cedula:
             return False, "Error: Nombres, Apellidos y Cédula son requeridos."
        if sexo and sexo not in ['Femenino', 'Masculino', 'Otro', '']:
             return False, "Error: Valor inválido para Sexo."


        # --- Conexión y Transacción ---
        conn = None
        try:
            conn = database.connect_db()
            with conn: # Transacción automática
                cursor = conn.cursor()

                # --- Encriptar datos ---
                # ... (encriptar todos los campos necesarios como antes) ...
                nombres_enc = database.encrypt_data(nombres)
                apellidos_enc = database.encrypt_data(apellidos)
                cedula_enc = database.encrypt_data(cedula)
                lugar_nac_enc = database.encrypt_data(lugar_nacimiento)
                estado_civil_enc = database.encrypt_data(estado_civil)
                tel_hab_enc = database.encrypt_data(telefono_habitacion)
                tel_mov_enc = database.encrypt_data(telefono_movil)
                email_enc = database.encrypt_data(email)
                direccion_enc = database.encrypt_data(direccion)
                profesion_enc = database.encrypt_data(profesion_oficio)
                emerg_nombre_enc = database.encrypt_data(emerg_nombre)
                emerg_tel_enc = database.encrypt_data(emerg_telefono)
                emerg_parent_enc = database.encrypt_data(emerg_parentesco)
                emerg_dir_enc = database.encrypt_data(emerg_direccion)
                notas_enc = database.encrypt_data(notas_adicionales)

                fecha_modificacion = datetime.now()

                # --- Construir y Ejecutar UPDATE ---
                # ... (SQL UPDATE como antes, asegurando que todos los campos y '?' coincidan) ...
                sql = """
                    UPDATE Pacientes SET
                        nombres = ?, apellidos = ?, cedula = ?, sexo = ?, fecha_nacimiento = ?,
                        lugar_nacimiento = ?, estado_civil = ?, telefono_habitacion = ?, telefono_movil = ?, email = ?,
                        direccion = ?, profesion_oficio = ?, 
                        emerg_nombre = ?, emerg_telefono = ?, emerg_parentesco = ?, emerg_direccion = ?,
                        notas_adicionales = ?,
                        fecha_ultima_mod = ?, usuario_ultima_mod_id = ? 
                    WHERE id = ?
                """
                values = (
                    nombres_enc, apellidos_enc, cedula_enc, sexo, fecha_nacimiento,
                    lugar_nac_enc, estado_civil_enc, tel_hab_enc, tel_mov_enc, email_enc,
                    direccion_enc, profesion_enc,
                    emerg_nombre_enc, emerg_tel_enc, emerg_parent_enc, emerg_dir_enc,
                    notas_enc,
                    fecha_modificacion, current_user_id, 
                    patient_id # <<< Usar el ID convertido a entero
                )
                cursor.execute(sql, values)

                if cursor.rowcount == 0:
                     print(f"PacienteActions WARN: No se encontró Paciente ID {patient_id} para actualizar.")
                     return False, f"Error: Paciente con ID {patient_id} no encontrado."

                print(f"PacienteActions: Datos básicos del Paciente ID {patient_id} actualizados.")

                # --- Registrar Acción en Historial ---
                # ... (log_action como antes) ...
                log_descripcion = f"Usuario ID {current_user_id} actualizó datos básicos del paciente ID {patient_id}."
                database.log_action(
                    db_conn=conn, usuario_id=current_user_id, tipo_accion="ACTUALIZAR_PACIENTE_BASICO",
                    descripcion=log_descripcion, tabla="Pacientes", registro_id=patient_id,
                    detalles={'campos_modificados': list(patient_data.keys())} 
                )

            print("PacienteActions: Transacción de actualización completada.")
            return True, "Datos del paciente actualizados exitosamente."

        # ... (bloques except como antes) ...
        except sqlite3.IntegrityError as e:
             print(f"PacienteActions DB Integrity Error en UPDATE: {e}")
             if "UNIQUE constraint failed: Pacientes.cedula" in str(e):
                  return False, f"Error: La cédula '{cedula}' ya está registrada para otro paciente."
             else:
                 return False, f"Error de base de datos al actualizar: {e}"
        except Exception as e:
            print(f"PacienteActions General Error en UPDATE: {e}"); traceback.print_exc()
            return False, f"Error inesperado al actualizar datos básicos: {e}"
        finally:
            if conn: conn.close()
    
    def get_ingreso_details(self, patient_id: int, consulta_id: int):
        print(f"PatientActions: Obteniendo detalles de INGRESO Y ANTECEDENTES para Paciente ID: {patient_id}, Consulta ID: {consulta_id}")
        conn = None
        # Estructura de datos más completa
        full_details = {
            "paciente_id_original": patient_id,
            "consulta_id_original": consulta_id,
            "paciente_info": {}, # Para datos generales del paciente, incluyendo antecedentes
            "consulta_data": {},
            "examen_fisico_data": {},
            "error": None
        }

        try:
            conn = database.connect_db()
            if not conn:
                full_details["error"] = "Fallo de conexión a la base de datos."
                return full_details
            
            cursor = conn.cursor()
            cursor.row_factory = sqlite3.Row

            # 1. Obtener TODOS los datos relevantes del Paciente (incluyendo antecedentes)
            #    Usa las claves de tu 'paciente_sql_data' como referencia para los campos de la tabla Pacientes
            campos_paciente = [
                "id", "nombres", "apellidos", "numero_historia", "cedula", "sexo", 
                "fecha_nacimiento", "lugar_nacimiento", "estado_civil", 
                "telefono_habitacion", "telefono_movil", "email", "direccion", 
                "profesion_oficio", "emerg_nombre", "emerg_telefono", "emerg_parentesco", 
                "emerg_direccion", "notas_adicionales",
                "ap_asma", "ap_hta", "ap_dm", "ap_cardiopatia", "ap_otros", # Asumiendo que tienes ap_cardiopatia
                "ap_asma_detalle", "ap_hta_detalle", "ap_dm_detalle", "ap_cardiopatia_detalle", "ap_otros_detalle",
                "ap_alergias", "ap_quirurgicos",
                "af_madre", "af_padre", "af_hermanos", "af_hijos",
                "hab_tabaco", "hab_alcohol", "hab_drogas", "hab_cafe"
                # Añade cualquier otro campo de Pacientes que necesites
            ]
            campos_paciente_str = ", ".join(campos_paciente)
            cursor.execute(f"SELECT {campos_paciente_str} FROM Pacientes WHERE id = ?", (patient_id,))
            paciente_row = cursor.fetchone()
            
            if paciente_row:
                temp_paciente_info = {}
                for key in paciente_row.keys(): # Itera sobre las columnas recuperadas
                    value = paciente_row[key]
                    # Campos que son flags booleanos/enteros y no necesitan desencriptación para el form
                    flag_fields = ["ap_asma", "ap_hta", "ap_dm", "ap_cardiopatia", "ap_otros"]
                    # Campos que son de texto plano o fechas y no necesitan desencriptación para el form
                    plain_text_or_date_fields = ["id", "numero_historia", "sexo", "fecha_nacimiento"]

                    if key in flag_fields or key in plain_text_or_date_fields:
                        temp_paciente_info[key] = value
                    elif isinstance(value, bytes): # Asumir que el resto de los BLOBs son encriptados
                        try:
                            dec_val = database.decrypt_data(value)
                            temp_paciente_info[f"{key}_dec"] = dec_val
                        except:
                            temp_paciente_info[f"{key}_dec"] = "[Error Decrypt]"
                            temp_paciente_info[key] = value # Mantener blob si falla
                    else: # Otros tipos (ej. texto ya desencriptado o que no era blob)
                         temp_paciente_info[key] = value
                
                full_details["paciente_info"] = temp_paciente_info
                # Para la cabecera del formulario, seguimos usando nombres específicos
                full_details["paciente_nombre_completo"] = f"{temp_paciente_info.get('nombres_dec','')} {temp_paciente_info.get('apellidos_dec','')}".strip()
                full_details["paciente_numero_historia"] = temp_paciente_info.get("numero_historia")
            else:
                full_details["error"] = f"Paciente con ID {patient_id} no encontrado."
                # Si no hay paciente, no tiene sentido seguir.
                if conn: conn.close()
                return full_details


            # 2. Obtener datos de la Consulta (como antes)
            cursor.execute("SELECT * FROM Consultas WHERE id = ? AND paciente_id = ?", (consulta_id, patient_id))
            consulta_row = cursor.fetchone()
            if consulta_row:
                temp_consulta_data = {}
                for key in consulta_row.keys():
                    value = consulta_row[key]
                    blob_fields_consulta = ['motivo_consulta', 'historia_enfermedad_actual', 'diagnostico_ingreso']
                    if key in blob_fields_consulta and isinstance(value, bytes):
                        try: temp_consulta_data[f"{key}_dec"] = database.decrypt_data(value)
                        except: temp_consulta_data[f"{key}_dec"] = "[Error Decrypt]"; temp_consulta_data[key] = value
                    else: temp_consulta_data[key] = value
                full_details["consulta_data"] = temp_consulta_data
            else:
                # ... (manejo de error si la consulta no se encuentra) ...
                current_error = full_details["error"]
                error_msg_consulta = f"Consulta ID {consulta_id} para Paciente ID {patient_id} no encontrada."
                full_details["error"] = f"{current_error} | {error_msg_consulta}" if current_error else error_msg_consulta

            # 3. Obtener datos del Examen Físico (como antes)
            cursor.execute("SELECT * FROM ExamenesFisicos WHERE consulta_id = ?", (consulta_id,))
            ef_row = cursor.fetchone()
            if ef_row:
                temp_ef_data = {}
                for key in ef_row.keys():
                    value = ef_row[key]
                    blob_fields_ef = ['ef_ta', 'ef_temp', 'ef_piel', 'ef_respiratorio', 'ef_cardiovascular', 'ef_abdomen', 'ef_gastrointestinal', 'ef_genitourinario', 'ef_extremidades', 'ef_neurologico', 'ef_otros_hallazgos']
                    numeric_fields_ef = ['ef_fc', 'ef_fr', 'ef_sato2', 'ef_glic']
                    if key in blob_fields_ef and isinstance(value, bytes):
                        try: temp_ef_data[f"{key}_dec"] = database.decrypt_data(value)
                        except: temp_ef_data[f"{key}_dec"] = "[Error Decrypt]"; temp_ef_data[key] = value
                    elif key in numeric_fields_ef or key in ['id', 'consulta_id']:
                        temp_ef_data[key] = value
                    else: temp_ef_data[key] = value
                full_details["examen_fisico_data"] = temp_ef_data
            
            print(f"PatientActions: Detalles COMPLETOS (incl. antecedentes) recuperados: {json.dumps(full_details, default=str, indent=2)}")

        except sqlite3.Error as db_err:
            full_details["error"] = f"Error de base de datos: {db_err}"
            print(f"DB Error get_ingreso_details_COMPLETO: {db_err}"); traceback.print_exc()
        except Exception as e:
            full_details["error"] = f"Error inesperado: {e}"
            print(f"Error get_ingreso_details_COMPLETO: {e}"); traceback.print_exc()
        finally:
            if conn: conn.close()
        
        return full_details


    def update_ingreso_data(self, data_dict: dict, current_user_id: int):
        print(f"PatientActions: Iniciando actualización de DATOS DE INGRESO Y ANTECEDENTES DEL PACIENTE...")

        try:
            patient_id = int(data_dict.get('patient_id'))
            consulta_id = int(data_dict.get('consulta_id'))
            examen_fisico_id_str = data_dict.get('examen_fisico_id', '')
            examen_fisico_id = int(examen_fisico_id_str) if examen_fisico_id_str and examen_fisico_id_str.isdigit() else None
        except (ValueError, TypeError) as e:
            return False, f"Error: IDs de paciente/consulta inválidos: {e}"

        if not all([patient_id, consulta_id, data_dict.get('motivo_consulta'), data_dict.get('historia_enfermedad_actual')]):
            return False, "Error: Faltan IDs o campos requeridos de ingreso (Motivo, HEA)."

        conn = None
        try:
            conn = database.connect_db()
            with conn: # Transacción automática
                cursor = conn.cursor()
                now = datetime.now()

                # === 1. Actualizar ANTECEDENTES en la tabla Pacientes ===
                antecedentes_fields_to_update = {}
                # Mapea los nombres de los campos del formulario a las columnas de la BD
                # y encripta si es necesario.
                # Basado en tu paciente_sql_data (ajusta según los nombres de tus inputs HTML)
                campos_antecedentes_paciente = {
                    "ap_asma": data_dict.get('ap_asma'), # Será 1 o 0 desde el form
                    "ap_hta": data_dict.get('ap_hta'),
                    "ap_dm": data_dict.get('ap_dm'),
                    "ap_cardiopatia": data_dict.get('ap_cardiopatia'), # Si lo tienes
                    "ap_otros": data_dict.get('ap_otros'),
                    "ap_asma_detalle": database.encrypt_data(data_dict.get('ap_asma_detalle')),
                    "ap_hta_detalle": database.encrypt_data(data_dict.get('ap_hta_detalle')),
                    "ap_dm_detalle": database.encrypt_data(data_dict.get('ap_dm_detalle')),
                    "ap_cardiopatia_detalle": database.encrypt_data(data_dict.get('ap_cardiopatia_detalle')), # Si lo tienes
                    "ap_otros_detalle": database.encrypt_data(data_dict.get('ap_otros_detalle')),
                    "ap_alergias": database.encrypt_data(data_dict.get('ap_alergias')),
                    "ap_quirurgicos": database.encrypt_data(data_dict.get('ap_quirurgicos')),
                    "af_madre": database.encrypt_data(data_dict.get('af_madre')),
                    "af_padre": database.encrypt_data(data_dict.get('af_padre')),
                    "af_hermanos": database.encrypt_data(data_dict.get('af_hermanos')),
                    "af_hijos": database.encrypt_data(data_dict.get('af_hijos')),
                    "hab_tabaco": database.encrypt_data(data_dict.get('hab_tabaco')),
                    "hab_alcohol": database.encrypt_data(data_dict.get('hab_alcohol')),
                    "hab_drogas": database.encrypt_data(data_dict.get('hab_drogas')),
                    "hab_cafe": database.encrypt_data(data_dict.get('hab_cafe')),
                }
                # Filtrar campos que realmente se enviaron (no None) para evitar sobreescribir con NULL innecesariamente
                # O decide si quieres que un campo vacío en el form ponga NULL en la BD
                for key, value in campos_antecedentes_paciente.items():
                    if value is not None: # O una comprobación más estricta si es necesario
                        antecedentes_fields_to_update[key] = value
                
                if antecedentes_fields_to_update: # Solo actualizar si hay campos de antecedentes para cambiar
                    antecedentes_fields_to_update["fecha_ultima_mod"] = now
                    antecedentes_fields_to_update["usuario_ultima_mod_id"] = current_user_id
                    
                    set_clause_pac = ", ".join([f"{key} = ?" for key in antecedentes_fields_to_update.keys()])
                    sql_pac = f"UPDATE Pacientes SET {set_clause_pac} WHERE id = ?"
                    values_pac = list(antecedentes_fields_to_update.values()) + [patient_id]
                    cursor.execute(sql_pac, values_pac)
                    if cursor.rowcount > 0:
                        print(f"PatientActions: Antecedentes actualizados para Paciente ID {patient_id}.")
                    # else: Podrías loguear si el paciente no se encontró, aunque sería raro en este flujo


                # === 2. Actualizar tabla Consultas (como antes) ===
                consulta_fields_to_update = {
                    "motivo_consulta": database.encrypt_data(data_dict.get('motivo_consulta')),
                    "historia_enfermedad_actual": database.encrypt_data(data_dict.get('historia_enfermedad_actual')),
                    "diagnostico_ingreso": database.encrypt_data(data_dict.get('diagnostico_ingreso')),
                    "fecha_ultima_mod": now,
                    "usuario_ultima_mod_id": current_user_id
                }
                # ... (resto de tu lógica para actualizar Consultas) ...
                set_clause_con = ", ".join([f"{key} = ?" for key in consulta_fields_to_update.keys()])
                sql_con = f"UPDATE Consultas SET {set_clause_con} WHERE id = ? AND paciente_id = ?"
                values_con = list(consulta_fields_to_update.values()) + [consulta_id, patient_id]
                cursor.execute(sql_con, values_con)
                if cursor.rowcount == 0: return False, f"Error: Consulta ID {consulta_id} no encontrada para Paciente ID {patient_id}."

                # === 3. Actualizar o Insertar en ExamenesFisicos (como antes) ===
                # ... (tu lógica existente para ef_fields, has_ef_data, UPDATE e INSERT de ExamenesFisicos) ...
                # (La copié de tu código anterior, asegúrate que sea la correcta)
                ef_fields = { # Re-mapeo para asegurar que los nombres de form a BD sean correctos
                    "ef_ta": database.encrypt_data(data_dict.get('ef_ta')),
                    "ef_fc": data_dict.get('ef_fc') or None, 
                    "ef_fr": data_dict.get('ef_fr') or None,
                    "ef_sato2": data_dict.get('ef_sato2') or None,
                    "ef_temp": database.encrypt_data(data_dict.get('ef_temp')),
                    "ef_glic": data_dict.get('ef_glic') or None,
                    "ef_piel": database.encrypt_data(data_dict.get('ef_piel')),
                    "ef_respiratorio": database.encrypt_data(data_dict.get('ef_respiratorio')),
                    "ef_cardiovascular": database.encrypt_data(data_dict.get('ef_cardiovascular')),
                    "ef_abdomen": database.encrypt_data(data_dict.get('ef_abdomen')),
                    "ef_gastrointestinal": database.encrypt_data(data_dict.get('ef_gastrointestinal')),
                    "ef_genitourinario": database.encrypt_data(data_dict.get('ef_genitourinario')),
                    "ef_extremidades": database.encrypt_data(data_dict.get('ef_extremidades')),
                    "ef_neurologico": database.encrypt_data(data_dict.get('ef_neurologico')),
                    "ef_otros_hallazgos": database.encrypt_data(data_dict.get('ef_otros_hallazgos')),
                    "fecha_hora": now 
                }
                has_ef_data = any( (v is not None and v != b'' and v != '') for k,v in ef_fields.items() if k != "fecha_hora" )
                if has_ef_data:
                    if examen_fisico_id: # Update
                        ef_set_clause = ", ".join([f"{k} = ?" for k in ef_fields.keys()])
                        ef_sql = f"UPDATE ExamenesFisicos SET {ef_set_clause} WHERE id = ? AND consulta_id = ?"
                        ef_values = list(ef_fields.values()) + [examen_fisico_id, consulta_id]
                        cursor.execute(ef_sql, ef_values)
                        if cursor.rowcount == 0: examen_fisico_id = None # Forzar insert si no se actualizó
                    if not examen_fisico_id: # Insert
                        ef_fields["consulta_id"] = consulta_id
                        ef_cols = ", ".join(ef_fields.keys())
                        ef_placeholders = ", ".join(["?"] * len(ef_fields))
                        ef_sql_insert = f"INSERT INTO ExamenesFisicos ({ef_cols}) VALUES ({ef_placeholders})"
                        cursor.execute(ef_sql_insert, tuple(ef_fields.values()))

                # === 4. Registrar Acción en Historial ===
                log_descripcion = f"Actualizó datos de ingreso y/o antecedentes del paciente. Consulta ID {consulta_id} (Paciente ID {patient_id})."
                log_action(
                    db_conn=conn, usuario_id=current_user_id, tipo_accion="ACTUALIZAR_INGRESO_Y_PACIENTE",
                    descripcion=log_descripcion, tabla="Pacientes, Consultas, ExamenesFisicos", registro_id=patient_id,
                    detalles={'consulta_id': consulta_id, 'patient_id': patient_id}
                )

            print("PatientActions: Transacción de actualización (ingreso y antecedentes) completada.")
            return True, "Datos del paciente e ingreso actualizados exitosamente."

        # ... (bloques except y finally) ...
        except sqlite3.Error as db_err: # ...
            return False, f"Error de BD: {db_err}"
        except Exception as e: # ...
            return False, f"Error inesperado: {e}"
        finally:
            if conn: conn.close()

    def add_new_evolucion(self, evolucion_data: dict, patient_id: int, consulta_id: int, current_user_id: int):
        """
        Añade una nueva evolución médica.
        """
        print(f"PatientActions: Iniciando añadir NUEVA EVOLUCION para Paciente ID: {patient_id}, Consulta ID: {consulta_id}")

        if not all([evolucion_data.get('ev_subjetivo'), evolucion_data.get('ev_objetivo'),
                    evolucion_data.get('ev_diagnosticos'), evolucion_data.get('ev_tratamiento_plan')]):
            return False, "Error: Subjetivo, Objetivo (Aspecto General), Diagnósticos y Plan son requeridos.", None
        
        # Asumo que paciente_id NO está en la tabla Evoluciones directamente, sino que se relaciona a través de consulta_id.
        # Si tienes paciente_id en Evoluciones, descomenta la validación y la inserción.
        # if not patient_id:
        #     return False, "Error: ID de Paciente inválido.", None
        if not consulta_id or not current_user_id:
            return False, "Error: IDs de Consulta o Usuario inválidos.", None

        conn = None
        new_evolucion_id = None
        try:
            conn = database.connect_db()
            with conn:
                cursor = conn.cursor()

                # Campos de la tabla Evoluciones (según tu CREATE TABLE)
                sql_data = {
                    "consulta_id": consulta_id,
                    "usuario_id": current_user_id,
                    "fecha_hora": datetime.now().isoformat(),
                    # "dias_hospitalizacion": evolucion_data.get('dias_hospitalizacion'), # Si lo manejas desde el form

                    # Signos Vitales
                    "ev_ta": database.encrypt_data(evolucion_data.get('ev_ta')),
                    "ev_fc": evolucion_data.get('ev_fc') if str(evolucion_data.get('ev_fc','')).strip() else None,
                    "ev_fr": evolucion_data.get('ev_fr') if str(evolucion_data.get('ev_fr','')).strip() else None,
                    "ev_sato2": evolucion_data.get('ev_sato2') if str(evolucion_data.get('ev_sato2','')).strip() else None,
                    "ev_temp": database.encrypt_data(evolucion_data.get('ev_temp')),
                    
                    # Campos SOAP
                    "ev_subjetivo": database.encrypt_data(evolucion_data['ev_subjetivo']),
                    "ev_objetivo": database.encrypt_data(evolucion_data['ev_objetivo']), # Aspecto General / Hallazgos Principales
                    
                    # Campos Detallados del Examen Físico
                    "ev_piel": database.encrypt_data(evolucion_data.get('ev_piel')),
                    "ev_respiratorio": database.encrypt_data(evolucion_data.get('ev_respiratorio')),
                    "ev_cardiovascular": database.encrypt_data(evolucion_data.get('ev_cardiovascular')),
                    "ev_abdomen": database.encrypt_data(evolucion_data.get('ev_abdomen')),
                    "ev_extremidades": database.encrypt_data(evolucion_data.get('ev_extremidades')),
                    "ev_neurologico": database.encrypt_data(evolucion_data.get('ev_neurologico')),
                    "ev_otros": database.encrypt_data(evolucion_data.get('ev_otros')), # Otros hallazgos del EF
                    
                    "ev_diagnosticos": database.encrypt_data(evolucion_data['ev_diagnosticos']),
                    "ev_tratamiento_plan": database.encrypt_data(evolucion_data['ev_tratamiento_plan']),
                    "ev_comentario": database.encrypt_data(evolucion_data.get('ev_comentario')),
                    
                    # 'fecha_ultima_mod' y 'usuario_ultima_mod_id' se llenan en UPDATE
                }
                
                # Filtrar claves con valor None si tu BD no los acepta o quieres omitirlos
                # sql_data_filtered = {k: v for k, v in sql_data.items() if v is not None}
                # Por ahora, se envían Nones si el campo numérico estaba vacío. SQLite los manejará como NULL.

                cols = ", ".join(sql_data.keys())
                placeholders = ", ".join(["?"] * len(sql_data))
                sql = f"INSERT INTO Evoluciones ({cols}) VALUES ({placeholders})"
                
                cursor.execute(sql, tuple(sql_data.values()))
                new_evolucion_id = cursor.lastrowid
                print(f"PatientActions: Nueva evolución insertada con ID: {new_evolucion_id}")

                log_action(conn, current_user_id, 'CREAR_EVOLUCION',
                           f"Nueva evolución ID {new_evolucion_id} para Consulta ID {consulta_id} (Paciente ID {patient_id}).", # Mantenemos patient_id en el log para contexto
                           tabla='Evoluciones', registro_id=new_evolucion_id)

            return True, "Evolución médica guardada exitosamente.", new_evolucion_id
        except sqlite3.Error as db_err:
            print(f"PatientActions DB Error (add_new_evolucion): {db_err}"); traceback.print_exc()
            return False, f"Error de base de datos al guardar evolución: {db_err}", None
        except Exception as e:
            print(f"PatientActions General Error (add_new_evolucion): {e}"); traceback.print_exc()
            return False, f"Error inesperado al guardar evolución: {e}", None
        finally:
            if conn: conn.close()

    def get_evolucion_details(self, evolucion_id: int):
        print(f"PatientActions: Obteniendo detalles para Evolución ID: {evolucion_id}")
        conn = None
        evolucion_details_dict = {"error": None} 

        try:
            conn = database.connect_db()
            cursor = conn.cursor()
            # La tabla Evoluciones no tiene paciente_id directamente según tu CREATE.
            # La relación es Evoluciones -> Consultas -> Pacientes
            cursor.execute("""
                SELECT e.*, 
                       p.nombres as paciente_nombres_enc, p.apellidos as paciente_apellidos_enc, p.numero_historia,
                       p.id as paciente_id_real,  -- Este es el ID del paciente desde la tabla Pacientes
                       c.fecha_hora_ingreso as paciente_fecha_ingreso_para_calculo, -- Fecha de ingreso de la consulta asociada
                       COALESCE(u_creador.nombre_completo, u_creador.nombre_usuario) as u_creador_nombre_completo_enc,
                       COALESCE(u_mod.nombre_completo, u_mod.nombre_usuario) as u_mod_nombre_completo_enc
                FROM Evoluciones e
                JOIN Consultas c ON e.consulta_id = c.id
                JOIN Pacientes p ON c.paciente_id = p.id
                JOIN Usuarios u_creador ON e.usuario_id = u_creador.id
                LEFT JOIN Usuarios u_mod ON e.usuario_ultima_mod_id = u_mod.id
                WHERE e.id = ?
            """, (evolucion_id,))
            
            row = cursor.fetchone()
            if not row:
                evolucion_details_dict["error"] = f"Evolución con ID {evolucion_id} no encontrada."
                return evolucion_details_dict

            colnames = [desc[0] for desc in cursor.description]
            raw_details = dict(zip(colnames, row))
            processed_details = {'id': raw_details['id']} # ID de la evolución

            # Campos a desencriptar si son BLOB
            fields_to_decrypt_if_blob = [
                'ev_subjetivo', 'ev_objetivo', 'ev_ta', 'ev_temp',
                'ev_piel', 'ev_respiratorio', 'ev_cardiovascular', 'ev_abdomen',
                'ev_extremidades', 'ev_neurologico', 'ev_otros',
                'ev_diagnosticos', 'ev_tratamiento_plan', 'ev_comentario',
                'paciente_nombres_enc', 'paciente_apellidos_enc', # Nombres del paciente
                'u_creador_nombre_completo_enc', 'u_mod_nombre_completo_enc' # Nombres de usuarios
            ]

            for key, value in raw_details.items():
                if key == 'id': continue # Ya está en processed_details

                if key in fields_to_decrypt_if_blob and isinstance(value, bytes):
                    try:
                        # Cambiar el nombre de la clave al agregar _dec para campos de paciente y usuario
                        if key == 'paciente_nombres_enc':
                            processed_details['paciente_nombres_dec'] = database.decrypt_data(value)
                        elif key == 'paciente_apellidos_enc':
                            processed_details['paciente_apellidos_dec'] = database.decrypt_data(value)
                        elif key == 'u_creador_nombre_completo_enc':
                            processed_details['usuario_creador_nombre_completo'] = database.decrypt_data(value)
                        elif key == 'u_mod_nombre_completo_enc':
                            processed_details['usuario_modificador_nombre_completo'] = database.decrypt_data(value)
                        else: # Para los campos ev_...
                            processed_details[f"{key}_dec"] = database.decrypt_data(value)
                    except Exception:
                        # Similarmente, manejar el nombre de la clave para el error
                        if key.endswith('_enc'):
                            processed_details[key.replace('_enc', '_dec')] = "[Error Decrypt]"
                        else:
                            processed_details[f"{key}_dec"] = "[Error Decrypt]"
                else:
                    # Copiar campos que no son BLOB o no necesitan desencriptación,
                    # o que ya tienen el nombre final (ej. paciente_id_real, numero_historia)
                    processed_details[key] = value
            
            # Si el nombre completo no vino como blob (porque no estaba encriptado en Usuarios o era NULL)
            # y el alias ya es _nombre_completo, asegurarse que esté.
            if 'u_creador_nombre_completo_enc' not in raw_details and 'usuario_creador_nombre_completo' not in processed_details:
                processed_details['usuario_creador_nombre_completo'] = raw_details.get('u_creador_nombre_completo_enc') # COALESCE ya dio el username
            if 'u_mod_nombre_completo_enc' not in raw_details and 'usuario_modificador_nombre_completo' not in processed_details:
                 processed_details['usuario_modificador_nombre_completo'] = raw_details.get('u_mod_nombre_completo_enc')

            evolucion_details_dict = processed_details
            print(f"PatientActions: Detalles de evolución ID {evolucion_id} recuperados.")
            
        except sqlite3.Error as db_err:
            evolucion_details_dict["error"] = f"Error de BD: {db_err}"
        except Exception as e:
            evolucion_details_dict["error"] = f"Error inesperado: {e}"
        finally:
            if conn: conn.close()
        return evolucion_details_dict

    def update_evolucion(self, evolucion_id: int, evolucion_data: dict, current_user_id: int):
        print(f"PatientActions: Iniciando ACTUALIZAR EVOLUCION ID: {evolucion_id}")

        if not evolucion_id: return False, "Error: ID de Evolución no proporcionado."
        if not all([evolucion_data.get('ev_subjetivo'), evolucion_data.get('ev_objetivo'),
                    evolucion_data.get('ev_diagnosticos'), evolucion_data.get('ev_tratamiento_plan')]):
            return False, "Error: Subjetivo, Objetivo (Aspecto General), Diagnósticos y Plan son requeridos."

        conn = None
        try:
            conn = database.connect_db()
            with conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()

                sql_data_to_update = {
                    # Signos Vitales
                    "ev_ta": database.encrypt_data(evolucion_data.get('ev_ta')),
                    "ev_fc": evolucion_data.get('ev_fc') if str(evolucion_data.get('ev_fc','')).strip() else None,
                    "ev_fr": evolucion_data.get('ev_fr') if str(evolucion_data.get('ev_fr','')).strip() else None,
                    "ev_sato2": evolucion_data.get('ev_sato2') if str(evolucion_data.get('ev_sato2','')).strip() else None,
                    "ev_temp": database.encrypt_data(evolucion_data.get('ev_temp')),
                    
                    # Campos SOAP
                    "ev_subjetivo": database.encrypt_data(evolucion_data['ev_subjetivo']),
                    "ev_objetivo": database.encrypt_data(evolucion_data['ev_objetivo']),
                    
                    # Campos Detallados del Examen Físico
                    "ev_piel": database.encrypt_data(evolucion_data.get('ev_piel')),
                    "ev_respiratorio": database.encrypt_data(evolucion_data.get('ev_respiratorio')),
                    "ev_cardiovascular": database.encrypt_data(evolucion_data.get('ev_cardiovascular')),
                    "ev_abdomen": database.encrypt_data(evolucion_data.get('ev_abdomen')),
                    "ev_extremidades": database.encrypt_data(evolucion_data.get('ev_extremidades')),
                    "ev_neurologico": database.encrypt_data(evolucion_data.get('ev_neurologico')),
                    "ev_otros": database.encrypt_data(evolucion_data.get('ev_otros')),
                    
                    "ev_diagnosticos": database.encrypt_data(evolucion_data['ev_diagnosticos']),
                    "ev_tratamiento_plan": database.encrypt_data(evolucion_data['ev_tratamiento_plan']),
                    "ev_comentario": database.encrypt_data(evolucion_data.get('ev_comentario')),
                    
                    "fecha_ultima_mod": now,
                    "usuario_ultima_mod_id": current_user_id
                }
                
                set_clause = ", ".join([f"{key} = ?" for key in sql_data_to_update.keys()])
                sql = f"UPDATE Evoluciones SET {set_clause} WHERE id = ?"
                values = list(sql_data_to_update.values()) + [evolucion_id]
                
                cursor.execute(sql, values)
                if cursor.rowcount == 0:
                    return False, f"Error: Evolución con ID {evolucion_id} no encontrada o datos sin cambios."

                print(f"PatientActions: Evolución ID {evolucion_id} actualizada.")
                log_action(conn, current_user_id, 'ACTUALIZAR_EVOLUCION',
                           f"Actualizada evolución ID {evolucion_id}.",
                           tabla='Evoluciones', registro_id=evolucion_id)
            
            return True, "Evolución médica actualizada exitosamente."
        except sqlite3.Error as db_err:
            print(f"PatientActions DB Error (update_evolucion): {db_err}"); traceback.print_exc()
            return False, f"Error de base de datos al actualizar evolución: {db_err}"
        except Exception as e:
            print(f"PatientActions General Error (update_evolucion): {e}"); traceback.print_exc()
            return False, f"Error inesperado al actualizar evolución: {e}"
        finally:
            if conn: conn.close()

    # ... (El resto de tus métodos de PatientActions, como update_ingreso_data que ya me pasaste)
    # Asegúrate de que tu método update_ingreso_data esté aquí también.
    def update_ingreso_data(self, data_dict: dict, current_user_id: int):
        # ... (El código de update_ingreso_data que me proporcionaste antes) ...
        # Solo me aseguro de que esté aquí para que el archivo sea completo.
        print(f"PatientActions: Iniciando actualización de DATOS DE INGRESO Y ANTECEDENTES DEL PACIENTE...")
        try:
            patient_id = int(data_dict.get('patient_id'))
            consulta_id = int(data_dict.get('consulta_id'))
            examen_fisico_id_str = data_dict.get('examen_fisico_id', '')
            examen_fisico_id = int(examen_fisico_id_str) if examen_fisico_id_str and examen_fisico_id_str.isdigit() else None
        except (ValueError, TypeError) as e:
            return False, f"Error: IDs de paciente/consulta inválidos: {e}"

        if not all([patient_id, consulta_id, data_dict.get('motivo_consulta'), data_dict.get('historia_enfermedad_actual')]):
            return False, "Error: Faltan IDs o campos requeridos de ingreso (Motivo, HEA)."

        conn = None
        try:
            conn = database.connect_db()
            with conn: # Transacción automática
                cursor = conn.cursor()
                now = datetime.now() # Usar datetime de datetime

                # === 1. Actualizar ANTECEDENTES en la tabla Pacientes ===
                antecedentes_fields_to_update = {}
                campos_antecedentes_paciente = {
                    "ap_asma": 1 if data_dict.get('ap_asma') else 0, 
                    "ap_hta": 1 if data_dict.get('ap_hta') else 0,
                    "ap_dm": 1 if data_dict.get('ap_dm') else 0,
                    "ap_cardiopatia": 1 if data_dict.get('ap_cardiopatia') else 0, 
                    "ap_otros": 1 if data_dict.get('ap_otros') else 0,
                    "ap_asma_detalle": database.encrypt_data(data_dict.get('ap_asma_detalle')),
                    "ap_hta_detalle": database.encrypt_data(data_dict.get('ap_hta_detalle')),
                    "ap_dm_detalle": database.encrypt_data(data_dict.get('ap_dm_detalle')),
                    "ap_cardiopatia_detalle": database.encrypt_data(data_dict.get('ap_cardiopatia_detalle')), 
                    "ap_otros_detalle": database.encrypt_data(data_dict.get('ap_otros_detalle')),
                    "ap_alergias": database.encrypt_data(data_dict.get('ap_alergias')),
                    "ap_quirurgicos": database.encrypt_data(data_dict.get('ap_quirurgicos')),
                    "af_madre": database.encrypt_data(data_dict.get('af_madre')),
                    "af_padre": database.encrypt_data(data_dict.get('af_padre')),
                    "af_hermanos": database.encrypt_data(data_dict.get('af_hermanos')),
                    "af_hijos": database.encrypt_data(data_dict.get('af_hijos')),
                    "hab_tabaco": database.encrypt_data(data_dict.get('hab_tabaco')),
                    "hab_alcohol": database.encrypt_data(data_dict.get('hab_alcohol')),
                    "hab_drogas": database.encrypt_data(data_dict.get('hab_drogas')),
                    "hab_cafe": database.encrypt_data(data_dict.get('hab_cafe')),
                }
                for key, value in campos_antecedentes_paciente.items():
                    # Para checkboxes, el valor será 0 o 1. Para textareas/inputs, None si no se llenaron.
                    # Decidimos si un string vacío en el form debe ser NULL o string vacío en BD.
                    # Aquí, si el valor es None (no enviado o explícitamente None), no lo incluimos en el UPDATE.
                    if key.startswith("ap_") and not key.endswith("_detalle"): # Flags
                         antecedentes_fields_to_update[key] = value # Siempre actualizar flags
                    elif value is not None: # Para campos de texto y detalles
                        antecedentes_fields_to_update[key] = value
                
                if antecedentes_fields_to_update:
                    antecedentes_fields_to_update["fecha_ultima_mod"] = now
                    antecedentes_fields_to_update["usuario_ultima_mod_id"] = current_user_id
                    
                    set_clause_pac = ", ".join([f"{key} = ?" for key in antecedentes_fields_to_update.keys()])
                    sql_pac = f"UPDATE Pacientes SET {set_clause_pac} WHERE id = ?"
                    values_pac = list(antecedentes_fields_to_update.values()) + [patient_id]
                    cursor.execute(sql_pac, values_pac)
                    if cursor.rowcount > 0:
                        print(f"PatientActions: Antecedentes actualizados para Paciente ID {patient_id}.")

                # === 2. Actualizar tabla Consultas ===
                consulta_fields_to_update = {
                    "motivo_consulta": database.encrypt_data(data_dict.get('motivo_consulta')),
                    "historia_enfermedad_actual": database.encrypt_data(data_dict.get('historia_enfermedad_actual')),
                    "diagnostico_ingreso": database.encrypt_data(data_dict.get('diagnostico_ingreso')),
                    "fecha_ultima_mod": now.isoformat(), # Guardar como ISO string
                    "usuario_ultima_mod_id": current_user_id
                }
                set_clause_con = ", ".join([f"{key} = ?" for key in consulta_fields_to_update.keys()])
                sql_con = f"UPDATE Consultas SET {set_clause_con} WHERE id = ? AND paciente_id = ?"
                values_con = list(consulta_fields_to_update.values()) + [consulta_id, patient_id]
                cursor.execute(sql_con, values_con)
                if cursor.rowcount == 0: return False, f"Error: Consulta ID {consulta_id} no encontrada para Paciente ID {patient_id}."

                # === 3. Actualizar o Insertar en ExamenesFisicos ===
                ef_fields = {
                    "ef_ta": database.encrypt_data(data_dict.get('ef_ta')),
                    "ef_fc": data_dict.get('ef_fc') if str(data_dict.get('ef_fc','')).strip() else None, 
                    "ef_fr": data_dict.get('ef_fr') if str(data_dict.get('ef_fr','')).strip() else None,
                    "ef_sato2": data_dict.get('ef_sato2') if str(data_dict.get('ef_sato2','')).strip() else None,
                    "ef_temp": database.encrypt_data(data_dict.get('ef_temp')),
                    "ef_glic": data_dict.get('ef_glic') if str(data_dict.get('ef_glic','')).strip() else None,
                    "ef_piel": database.encrypt_data(data_dict.get('ef_piel')),
                    "ef_respiratorio": database.encrypt_data(data_dict.get('ef_respiratorio')),
                    "ef_cardiovascular": database.encrypt_data(data_dict.get('ef_cardiovascular')),
                    "ef_abdomen": database.encrypt_data(data_dict.get('ef_abdomen')),
                    "ef_gastrointestinal": database.encrypt_data(data_dict.get('ef_gastrointestinal')),
                    "ef_genitourinario": database.encrypt_data(data_dict.get('ef_genitourinario')),
                    "ef_extremidades": database.encrypt_data(data_dict.get('ef_extremidades')),
                    "ef_neurologico": database.encrypt_data(data_dict.get('ef_neurologico')),
                    "ef_otros_hallazgos": database.encrypt_data(data_dict.get('ef_otros_hallazgos')),
                    "fecha_hora": now.isoformat() # Guardar como ISO string
                }
                # Comprobar si hay algún dato significativo para el examen físico
                has_ef_data = any( (str(v).strip() != '' and v is not None and v != b'') for k,v in ef_fields.items() if k != "fecha_hora" )

                if has_ef_data:
                    if examen_fisico_id: # Update
                        ef_set_clause = ", ".join([f"{k} = ?" for k in ef_fields.keys()])
                        ef_sql = f"UPDATE ExamenesFisicos SET {ef_set_clause} WHERE id = ? AND consulta_id = ?"
                        ef_values = list(ef_fields.values()) + [examen_fisico_id, consulta_id]
                        cursor.execute(ef_sql, ef_values)
                        if cursor.rowcount == 0: # Si no se actualizó (ej. ID incorrecto), intentar insertar
                            print(f"WARN: No se actualizó ExamenFisico ID {examen_fisico_id}, podría no existir. Se intentará insertar.")
                            examen_fisico_id = None 
                    
                    if not examen_fisico_id: # Insert
                        ef_fields_insert = ef_fields.copy() # Copiar para no modificar el original
                        ef_fields_insert["consulta_id"] = consulta_id
                        ef_cols = ", ".join(ef_fields_insert.keys())
                        ef_placeholders = ", ".join(["?"] * len(ef_fields_insert))
                        ef_sql_insert = f"INSERT INTO ExamenesFisicos ({ef_cols}) VALUES ({ef_placeholders})"
                        cursor.execute(ef_sql_insert, tuple(ef_fields_insert.values()))
                        print(f"PatientActions: Nuevo ExamenFisico insertado para Consulta ID {consulta_id}.")
                else: # Si no hay datos de EF y existía un registro, ¿deberíamos borrarlo? Por ahora no.
                    print("PatientActions: No hay datos significativos para Examen Físico, no se guardará/actualizará.")


                log_action(
                    db_conn=conn, usuario_id=current_user_id, tipo_accion="ACTUALIZAR_INGRESO_Y_PACIENTE",
                    descripcion=f"Actualizó datos de ingreso y/o antecedentes del paciente. Consulta ID {consulta_id} (Paciente ID {patient_id}).", 
                    tabla="Pacientes, Consultas, ExamenesFisicos", registro_id=patient_id,
                    detalles={'consulta_id': consulta_id, 'patient_id': patient_id}
                )

            print("PatientActions: Transacción de actualización (ingreso y antecedentes) completada.")
            return True, "Datos del paciente e ingreso actualizados exitosamente."
        except sqlite3.Error as db_err:
            print(f"PatientActions DB Error (update_ingreso_data): {db_err}"); traceback.print_exc()
            if conn: conn.rollback()
            return False, f"Error de base de datos: {db_err}"
        except Exception as e:
            print(f"PatientActions General Error (update_ingreso_data): {e}"); traceback.print_exc()
            if conn: conn.rollback()
            return False, f"Error inesperado: {e}"
        finally:
            if conn: conn.close()

    def get_patient_basic_info(self, patient_id: int):
        """
        Obtiene nombre completo y número de historia de un paciente por su ID.
        Retorna un diccionario con los datos o con un error.
        """
        print(f"PatientActions: Buscando info básica para Paciente ID: {patient_id}")
        conn = None
        info = {"error": None}
        if not patient_id or patient_id <= 0:
            info["error"] = "ID de paciente inválido."
            return info

        try:
            conn = database.connect_db()
            if not conn:
                info["error"] = "Fallo conexión DB."
                return info

            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, numero_historia, nombres, apellidos FROM Pacientes WHERE id = ?",
                (patient_id,)
            )
            row = cursor.fetchone()

            if row:
                paciente_id_db, numero_historia, nombres_enc, apellidos_enc = row
                nombre_completo = "Error Decrypt"
                try:
                    n_dec = database.decrypt_data(nombres_enc) if nombres_enc else ''
                    a_dec = database.decrypt_data(apellidos_enc) if apellidos_enc else ''
                    nombre_completo = f"{n_dec} {a_dec}".strip()
                except Exception as decrypt_err:
                    print(f"Error desencriptando nombre para ID {patient_id}: {decrypt_err}")
                    # nombre_completo se queda como "Error Decrypt"

                info = {
                    "id": paciente_id_db,
                    "nombre_completo": nombre_completo,
                    "numero_historia": numero_historia
                }
                print(f"PatientActions: Info básica encontrada: {info}")
            else:
                info["error"] = f"Paciente con ID {patient_id} no encontrado."
                print(info["error"])

            cursor.close()
            return info

        except sqlite3.Error as db_err:
            print(f"DB Error get_patient_basic_info: {db_err}"); traceback.print_exc()
            info["error"] = f"Error de base de datos: {db_err}"
            return info
        except Exception as e:
            print(f"Error get_patient_basic_info: {e}"); traceback.print_exc()
            info["error"] = f"Error inesperado: {e}"
            return info
        finally:
            if conn: conn.close()

    def get_latest_consulta_id_for_patient(self, patient_id: int):
        """
        Obtiene el ID de la consulta más reciente (basado en fecha_hora_ingreso)
        para un paciente específico.
        Retorna el ID de la consulta o None si no se encuentra.
        """
        print(f"PatientActions: Buscando última consulta para Paciente ID: {patient_id}")
        conn = None
        consulta_id = None
        if not patient_id or patient_id <= 0:
            print("PatientActions: ID de paciente inválido para get_latest_consulta_id.")
            return None

        try:
            conn = database.connect_db()
            if not conn:
                print("PatientActions: Fallo conexión DB para get_latest_consulta_id.")
                return None

            cursor = conn.cursor()
            # Asumiendo que tu tabla Consultas tiene una columna 'fecha_hora_ingreso'
            # y que es un timestamp o string que se puede ordenar cronológicamente.
            # Si el campo de fecha se llama diferente, ajústalo.
            cursor.execute(
                """
                SELECT id
                FROM Consultas
                WHERE paciente_id = ?
                ORDER BY fecha_hora_ingreso DESC
                LIMIT 1
                """,
                (patient_id,)
            )
            result = cursor.fetchone()

            if result:
                consulta_id = result[0]
                print(f"PatientActions: Última consulta ID encontrada: {consulta_id} para paciente {patient_id}")
            else:
                print(f"PatientActions: No se encontraron consultas para paciente {patient_id}")

        except sqlite3.Error as db_err:
            print(f"PatientActions DB Error (get_latest_consulta_id): {db_err}"); traceback.print_exc()
        except Exception as e:
            print(f"PatientActions General Error (get_latest_consulta_id): {e}"); traceback.print_exc()
        finally:
            if conn:
                conn.close()
        return consulta_id