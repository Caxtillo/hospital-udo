# historial_acciones.py
import sqlite3
import traceback
import database # Importar para acceso a BD y desencriptación (si es necesario)
from datetime import date, datetime
class HistorialActions:

    def get_log(self, page=1, per_page=50, filters=None): # Añadido filters (opcional)
        """
        Obtiene una lista paginada del historial de acciones.
        Realiza JOIN con Usuarios para obtener el nombre.
        Retorna: tuple (list[dict] | None, int: total_count)
        """
        print(f"HistorialActions: Obteniendo log (page: {page}, filters: {filters})")
        conn = None
        logs = []
        total_count = 0
        offset = (page - 1) * per_page

        # --- Query Base con JOIN ---
        # Seleccionamos campos de HistorialAcciones (ha) y nombre_usuario de Usuarios (u)
        # Nota: Usamos nombre_usuario (TEXT no encriptado) para evitar desencriptar aquí
        select_fields = """
            ha.id,
            ha.fecha_hora,
            ha.usuario_id,
            u.nombre_usuario,
            ha.tipo_accion,
            ha.tabla_afectada,
            ha.registro_afectado_id,
            ha.descripcion,
            ha.detalles_json
        """
        base_query = f"""
            SELECT {select_fields}
            FROM HistorialAcciones ha
            JOIN Usuarios u ON ha.usuario_id = u.id
        """
        count_query = """
            SELECT COUNT(ha.id)
            FROM HistorialAcciones ha
            JOIN Usuarios u ON ha.usuario_id = u.id
        """
        params = []
        where_clauses = []

        # --- Filtros (Ejemplo básico, puedes expandir) ---
        if filters:
            if filters.get('usuario_id'):
                where_clauses.append("ha.usuario_id = ?")
                params.append(filters['usuario_id'])
            if filters.get('tipo_accion'):
                where_clauses.append("ha.tipo_accion LIKE ?")
                params.append(f"%{filters['tipo_accion']}%")
            # Añadir filtros por fecha si es necesario...

        if where_clauses:
            sql_where = " WHERE " + " AND ".join(where_clauses)
            base_query += sql_where
            count_query += sql_where

        # --- Orden y Paginación ---
        base_query += f" ORDER BY ha.fecha_hora DESC LIMIT {per_page} OFFSET {offset}"

        try:
            conn = database.connect_db()
            if not conn: raise sqlite3.Error("Fallo conexión DB")
            cursor = conn.cursor()

            # Conteo Total (con filtros)
            print(f"HistorialActions: Count Query: {count_query} | Params: {params}")
            cursor.execute(count_query, params)
            total_count = cursor.fetchone()[0]
            print(f"HistorialActions: Conteo total: {total_count}")

            # Obtener logs de la página actual
            print(f"HistorialActions: Select Query: {base_query} | Params: {params}")
            cursor.execute(base_query, params)
            rows = cursor.fetchall()
            colnames = [desc[0] for desc in cursor.description]
            cursor.close()

            print(f"HistorialActions: {len(rows)} filas obtenidas. Formateando...")
            for row in rows:
                log_entry = dict(zip(colnames, row))
                # Formatear fecha/hora para display
                try:
                    # Crear objeto datetime desde string ISO (SQLite usualmente guarda así)
                    dt_obj = datetime.fromisoformat(log_entry['fecha_hora'])
                    # Formato deseado (ej: 25/05/2025 10:30:15)
                    log_entry['fecha_hora_formateada'] = dt_obj.strftime('%d/%m/%Y %H:%M:%S')
                except (ValueError, TypeError):
                    log_entry['fecha_hora_formateada'] = log_entry['fecha_hora'] # Mostrar original si falla

                # Desencriptar nombre_usuario si lo hubieras encriptado
                # (Actualmente no lo está, así que usamos el valor directo)
                # log_entry['nombre_usuario_dec'] = database.decrypt_data(log_entry['nombre_usuario'])

                logs.append(log_entry)

            print(f"HistorialActions: Procesamiento completo. Devolviendo {len(logs)} entradas.")
            return logs, total_count

        except sqlite3.Error as db_err:
            print(f"HistorialActions DB Error: {db_err}"); traceback.print_exc()
            return None, 0
        except Exception as e:
            print(f"HistorialActions Error: {e}"); traceback.print_exc()
            return None, 0
        finally:
            if conn: conn.close()