# historial_acciones.py
import sqlite3
import traceback
import database # Importar para acceso a BD y desencriptación
from datetime import datetime # Asegurar que datetime esté importado
import json # Para parsear detalles_json si es necesario

class HistorialActions:

    def _get_patient_name(self, cursor, patient_id):
        """Obtiene 'Nombres Apellidos (HC: XXXXXX)' para un patient_id."""
        if not patient_id: return "Paciente ID N/A"
        try:
            cursor.execute("SELECT nombres, apellidos, numero_historia FROM Pacientes WHERE id = ?", (patient_id,))
            row = cursor.fetchone()
            if row:
                nombres_enc, apellidos_enc, hc = row
                nombres = database.decrypt_data(nombres_enc) or "N/D"
                apellidos = database.decrypt_data(apellidos_enc) or ""
                return f"{nombres} {apellidos} (HC: {hc or 'N/A'})".strip()
            return f"Paciente ID {patient_id} (No encontrado)"
        except Exception as e:
            # print(f"Error obteniendo nombre de paciente ID {patient_id}: {e}")
            return f"Paciente ID {patient_id} (Error)"

    def _get_medico_name(self, cursor, medico_id):
        """Obtiene 'Nombre Completo (Usuario: X)' para un medico_id."""
        if not medico_id: return "Usuario ID N/A"
        try:
            cursor.execute("SELECT nombre_completo, nombre_usuario FROM Usuarios WHERE id = ?", (medico_id,))
            row = cursor.fetchone()
            if row:
                nombre_completo_enc, user_name = row
                nombre_completo = database.decrypt_data(nombre_completo_enc) or user_name
                return f"{nombre_completo} (Usuario: {user_name or 'N/A'})"
            return f"Usuario ID {medico_id} (No encontrado)"
        except Exception as e:
            # print(f"Error obteniendo nombre de médico ID {medico_id}: {e}")
            return f"Usuario ID {medico_id} (Error)"

    def get_log(self, page=1, per_page=50, filters=None):
        print(f"HistorialActions: Obteniendo log (page: {page}, filters: {filters})")
        conn = None
        logs = []
        total_count = 0
        offset = (page - 1) * per_page

        select_fields = """
            ha.id, ha.fecha_hora, ha.usuario_id, u.nombre_usuario AS actor_username,
            u.nombre_completo AS actor_nombre_completo_enc, /* Nombre del usuario que hizo la acción */
            ha.tipo_accion, ha.tabla_afectada, ha.registro_afectado_id,
            ha.descripcion AS descripcion_original, ha.detalles_json
        """
        base_query = f"""
            SELECT {select_fields}
            FROM HistorialAcciones ha
            LEFT JOIN Usuarios u ON ha.usuario_id = u.id /* Usar LEFT JOIN por si usuario_id es 0 para LOGIN_FALLIDO */
        """
        count_query = """
            SELECT COUNT(ha.id)
            FROM HistorialAcciones ha
            LEFT JOIN Usuarios u ON ha.usuario_id = u.id
        """
        params = []
        where_clauses = []

        if filters:
            # ... (tus filtros existentes) ...
            if filters.get('usuario_id'): # Filtrar por el usuario QUE REALIZÓ la acción
                where_clauses.append("ha.usuario_id = ?")
                params.append(filters['usuario_id'])
            if filters.get('tipo_accion'):
                where_clauses.append("ha.tipo_accion LIKE ?")
                params.append(f"%{filters['tipo_accion']}%")
            # Implementar filtros de fecha si es necesario
            if filters.get('fecha_desde'):
                where_clauses.append("ha.fecha_hora >= ?")
                params.append(filters['fecha_desde'] + " 00:00:00") # Asumir inicio del día
            if filters.get('fecha_hasta'):
                where_clauses.append("ha.fecha_hora <= ?")
                params.append(filters['fecha_hasta'] + " 23:59:59") # Asumir fin del día
            if filters.get('search_term'):
                # Buscar en la descripción original o en el nombre de usuario del actor
                where_clauses.append("(ha.descripcion LIKE ? OR u.nombre_usuario LIKE ?)")
                params.append(f"%{filters['search_term']}%")
                params.append(f"%{filters['search_term']}%")


        if where_clauses:
            sql_where = " WHERE " + " AND ".join(where_clauses)
            base_query += sql_where
            count_query += sql_where

        base_query += f" ORDER BY ha.fecha_hora DESC LIMIT {per_page} OFFSET {offset}"

        try:
            conn = database.connect_db()
            if not conn: raise sqlite3.Error("Fallo conexión DB")
            cursor = conn.cursor()

            cursor.execute(count_query, params)
            total_count_row = cursor.fetchone()
            total_count = total_count_row[0] if total_count_row else 0
            
            cursor.execute(base_query, params)
            rows = cursor.fetchall()
            colnames = [desc[0] for desc in cursor.description]
            
            for row in rows:
                log_entry = dict(zip(colnames, row))
                
                # Formatear fecha
                try:
                    dt_obj = datetime.fromisoformat(log_entry['fecha_hora'])
                    log_entry['fecha_hora_formateada'] = dt_obj.strftime('%d/%m/%Y %I:%M:%S %p') # Con AM/PM
                except: log_entry['fecha_hora_formateada'] = log_entry['fecha_hora']

                # Nombre del actor (usuario que realizó la acción)
                actor_nombre_completo = "Sistema/N/A"
                if log_entry.get('actor_nombre_completo_enc'):
                    try:
                        actor_nombre_completo = database.decrypt_data(log_entry['actor_nombre_completo_enc']) or log_entry.get('actor_username', 'N/D')
                    except: actor_nombre_completo = log_entry.get('actor_username', '[Err Decrypt]')
                elif log_entry.get('actor_username'): # Si no hay nombre completo encriptado, usa el username
                     actor_nombre_completo = log_entry.get('actor_username')

                log_entry['actor_display_name'] = actor_nombre_completo

                # Enriquecer descripción
                tipo_accion = log_entry['tipo_accion']
                tabla_afectada = log_entry['tabla_afectada']
                registro_id = log_entry['registro_afectado_id']
                descripcion_original = log_entry['descripcion_original']
                detalles = {}
                if log_entry.get('detalles_json'):
                    try: detalles = json.loads(log_entry['detalles_json'])
                    except: detalles = {}

                desc_entendible = descripcion_original # Empezar con la original

                if tipo_accion == 'CREAR_PACIENTE' and tabla_afectada == 'Pacientes' and registro_id:
                    paciente_nombre = self._get_patient_name(cursor, registro_id)
                    desc_entendible = f"Registró nuevo paciente: {paciente_nombre}."
                    if detalles.get('consulta_id'):
                        desc_entendible += f" Consulta inicial ID: {detalles['consulta_id']}."

                elif tipo_accion == 'ACTUALIZAR_PACIENTE_BASICO' and tabla_afectada == 'Pacientes' and registro_id:
                    paciente_nombre = self._get_patient_name(cursor, registro_id)
                    desc_entendible = f"Actualizó datos demográficos de: {paciente_nombre}."

                elif tipo_accion == 'CREAR_EVOLUCION' and tabla_afectada == 'Evoluciones' and registro_id:
                    paciente_id_evo = detalles.get('patient_id') # El patient_id se guarda en detalles
                    consulta_id_evo = detalles.get('consulta_id') # Asumiendo que también guardas esto
                    paciente_nombre_evo = self._get_patient_name(cursor, paciente_id_evo)
                    desc_entendible = f"Creó evolución ID {registro_id} para {paciente_nombre_evo} (Consulta ID: {consulta_id_evo or 'N/A'})."
                
                elif tipo_accion == 'ACTUALIZAR_EVOLUCION' and tabla_afectada == 'Evoluciones' and registro_id:
                    paciente_id_evo_upd = detalles.get('patient_id')
                    consulta_id_evo_upd = detalles.get('consulta_id')
                    paciente_nombre_evo_upd = self._get_patient_name(cursor, paciente_id_evo_upd)
                    desc_entendible = f"Actualizó evolución ID {registro_id} para {paciente_nombre_evo_upd} (Consulta ID: {consulta_id_evo_upd or 'N/A'})."

                elif tipo_accion == 'CREAR_ORDEN_MEDICA' and tabla_afectada == 'OrdenesMedicas' and registro_id:
                    paciente_id_om = detalles.get('paciente_id')
                    consulta_id_om = detalles.get('consulta_id')
                    paciente_nombre_om = self._get_patient_name(cursor, paciente_id_om)
                    desc_entendible = f"Creó orden médica ID {registro_id} para {paciente_nombre_om} (Consulta ID: {consulta_id_om or 'N/A'})."

                elif tipo_accion == 'ACTUALIZAR_ORDEN_MEDICA' and tabla_afectada == 'OrdenesMedicas' and registro_id:
                    paciente_id_om_upd = detalles.get('paciente_id')
                    # consulta_id_om_upd = detalles.get('consulta_id') # No siempre está en detalles de update
                    paciente_nombre_om_upd = self._get_patient_name(cursor, paciente_id_om_upd)
                    desc_entendible = f"Actualizó orden médica ID {registro_id} para {paciente_nombre_om_upd}."
                
                elif tipo_accion == 'ACTUALIZAR_INGRESO_Y_PACIENTE': # Este afecta múltiples tablas
                    paciente_id_ing = detalles.get('patient_id')
                    consulta_id_ing = detalles.get('consulta_id')
                    paciente_nombre_ing = self._get_patient_name(cursor, paciente_id_ing)
                    desc_entendible = f"Actualizó datos de ingreso/antecedentes para {paciente_nombre_ing} (Consulta ID: {consulta_id_ing or 'N/A'})."

                elif tipo_accion.startswith('ADD_USUARIO') and tabla_afectada == 'Usuarios' and registro_id:
                    medico_afectado = self._get_medico_name(cursor, registro_id)
                    desc_entendible = f"Añadió nuevo usuario: {medico_afectado}."
                
                elif tipo_accion.startswith('UPDATE_USUARIO') and tabla_afectada == 'Usuarios' and registro_id:
                    medico_afectado_upd = self._get_medico_name(cursor, registro_id)
                    desc_entendible = f"Actualizó datos del usuario: {medico_afectado_upd}."
                
                elif tipo_accion == 'TOGGLE_ESTADO_USUARIO' and tabla_afectada == 'Usuarios' and registro_id:
                    medico_afectado_toggle = self._get_medico_name(cursor, registro_id)
                    nuevo_estado = "Activado" if detalles.get('nuevo_estado') == 1 else "Desactivado"
                    desc_entendible = f"Cambió estado a '{nuevo_estado}' para el usuario: {medico_afectado_toggle}."
                
                # Para LOGIN_EXITOSO y LOGIN_FALLIDO, la descripción original suele ser suficiente
                # pero podrías añadir el nombre completo del usuario si es LOGIN_EXITOSO
                elif tipo_accion == 'LOGIN_EXITOSO' and log_entry.get('usuario_id') != 0:
                    # El actor_display_name ya tiene el nombre
                    desc_entendible = f"Inicio de sesión exitoso para: {log_entry['actor_display_name']}."
                elif tipo_accion == 'LOGOUT' and log_entry.get('usuario_id') != 0:
                    desc_entendible = f"Cierre de sesión para: {log_entry['actor_display_name']}."


                log_entry['descripcion_entendible'] = desc_entendible
                logs.append(log_entry)
            
            cursor.close() # Cerrar cursor después de todas las consultas
            return logs, total_count

        except sqlite3.Error as db_err:
            print(f"HistorialActions DB Error: {db_err}"); traceback.print_exc()
            return None, 0
        except Exception as e:
            print(f"HistorialActions Error: {e}"); traceback.print_exc()
            return None, 0
        finally:
            if conn: conn.close()