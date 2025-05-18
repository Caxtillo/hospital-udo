# main.py
import sys
import os # Necesitas 'os' para 'os.environ'
import traceback
import sqlite3
import json
import base64
import uuid


# --- IMPORTANTE: Configuración de Renderizado QtWebEngine ---
# OPCIÓN 3: Variables de Entorno (PARA PASAR ARGS A CHROMIUM SI setChromiumArgs NO EXISTE)
# ESTO DEBE IR ANTES DE CUALQUIER IMPORT DE PYQT6
# os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu --ignore-gpu-blacklist"
# print("INFO: Variable de entorno QTWEBENGINE_CHROMIUM_FLAGS establecida con: '--disable-gpu --ignore-gpu-blacklist'")

# Alternativamente, si la anterior no funciona y quieres forzar renderizado por software a nivel de Qt:
# os.environ["QT_OPENGL"] = "software"
# print("INFO: Variable de entorno QT_OPENGL=software establecida.")
# os.environ["QT_ANGLE_PLATFORM"] = "warp"
# print("INFO: Variable de entorno QT_ANGLE_PLATFORM=warp establecida.")

# OPCIÓN 1: Forzar Renderizado por Software OpenGL de Qt
# (DEBE IR ANTES DE QApplication, PERO DESPUÉS de los imports de PyQt6.QtCore)
# from PyQt6.QtCore import QCoreApplication, Qt as QtCoreQt # Importa QCoreApplication aquí
# QCoreApplication.setAttribute(QtCoreQt.ApplicationAttribute.AA_UseSoftwareOpenGL, True)
# print("INFO: AA_UseSoftwareOpenGL establecido en True.")

# --- Fin de Configuración de Renderizado QtWebEngine ---


# AHORA vienen los imports de PyQt6:
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl, QObject, pyqtSlot, pyqtSignal, QVariant, QCoreApplication, Qt as QtCoreQt # QCoreApplication y Qt se importan aquí
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog
from PyQt6.QtGui import QTextDocument


# Importar módulos locales
import database
import auth
# Importar la nueva clase de acciones de paciente
from paciente_acciones import PatientActions
from historial_acciones import HistorialActions
from medico_acciones import MedicoActions # <-- Importar

os.environ["QTWEBENGINE_REMOTE_DEBUGGING"] = "9223"
print("MainWindow: Depuración remota habilitada en http://localhost:9223 (si es soportado y no hay conflictos)")

# --- Backend Bridge Object ---
class BackendBridge(QObject):
    # Señales existentes
    login_success = pyqtSignal(dict)
    login_failed = pyqtSignal(str)
    viewContentLoaded = pyqtSignal(str, str)
    userDataLoaded = pyqtSignal(dict)
    # Señal para el resultado del guardado de paciente
    patientSaveResult = pyqtSignal(bool, str, str)
    nextHistoriaReady = pyqtSignal(str)
    patientListResult = pyqtSignal(list, int)
    actionLogResult = pyqtSignal(list, int) # log_list (o None), total_count
    medicoListResult = pyqtSignal(list, int) # Lista de médicos, total
    medicoAddResult = pyqtSignal(bool, str)  # success, message
    patientDetailsResult = pyqtSignal(str) # <<<--- AÑADIR ESTA LÍNEA
    selected_medico_id_to_edit = None # Variable para guardar el ID
    medicoDetailsResult = pyqtSignal(str)   # AHORA: Envía un string JSON
    medicoUpdateResult = pyqtSignal(bool, str)
    logoutComplete = pyqtSignal()
    medicoStatusToggleResult = pyqtSignal(bool, str, int, int)
    userDataLoaded = pyqtSignal(QVariant)
    updatePatientBasicDataResult = pyqtSignal(bool, str) # success, message
    ingresoDetailsResult = pyqtSignal(str) # o QVariant si envías un dict directamente
    updateIngresoDataResult = pyqtSignal(bool, str)
    evolucionSaveResult = pyqtSignal(bool, str, int) # success, message, new_evolucion_id (o None)
    evolucionDetailsResult = pyqtSignal(str)        # JSON string de los detalles o error
    evolucionUpdateResult = pyqtSignal(bool, str)   # success, message
    sendPatientInfoForAddEvolucion = pyqtSignal(str)
    ordenMedicaSaveResult = pyqtSignal(bool, str)
    ordenDetailsResult = pyqtSignal(str)

    def __init__(self, parent_window=None):
        super().__init__()
        self.parent_window = parent_window
        self.current_user_data = None
        # Crear instancia del manejador de acciones
        self.patient_manager = PatientActions()
        print("BackendBridge: Instancia de PatientActions creada.")
        self.historial_manager = HistorialActions()
        self.medico_manager = MedicoActions()
        self.selected_patient_id = None
        self.selected_medico_id_to_edit = None # Inicializar aquí también
        self.selected_consulta_id_for_edit = None
        self.selected_evolucion_id_for_view_edit = None
        self.patient_actions = PatientActions() # Asegúrate de tener la instancia
        self.selected_patient_id = None
        self.current_consulta_id = None
        self.db_manager = database

        selected_orden_id_for_view_edit = None
    # --- Funciones de utilidad interna ---
    def get_base_path(self):
        # Intenta obtener la ruta del directorio temporal de PyInstaller (_MEIPASS)
        # Si falla (ejecutando como script normal), usa el directorio del script actual
        try:
            # Para PyInstaller en modo one-file o one-dir (cuando está empaquetado)
            # sys._MEIPASS es la ruta al directorio temporal donde se desempaquetan los archivos
            base_path = sys._MEIPASS
        except AttributeError:
            # Ejecutando como script normal (no empaquetado)
            base_path = os.path.abspath(os.path.dirname(__file__))
        except Exception as e:
            print(f"WARN: Excepción obteniendo base_path (sys._MEIPASS): {e}. Usando fallback.")
            base_path = os.path.abspath(os.path.dirname(__file__))

        # Verificación adicional para modo one-dir si _MEIPASS no está definido
        # (esto es más para aplicaciones que pueden correr tanto empaquetadas como no)
        if not hasattr(sys, '_MEIPASS') and getattr(sys, 'frozen', False):
            # 'frozen' es True cuando PyInstaller empaqueta la app
            # En modo one-dir, sys.executable es la ruta al ejecutable principal
            base_path = os.path.dirname(sys.executable)
            print(f"INFO: Detectado modo 'one-dir' (frozen, no _MEIPASS). base_path ajustado a: {base_path}")

        # print(f"DEBUG: get_base_path() -> {base_path}")
        return base_path
    
    @pyqtSlot(int)
    def set_selected_orden(self, orden_id: int):
        print(f"BackendBridge: Orden seleccionada para ver/editar ID: {orden_id}")
        self.selected_orden_id_for_view_edit = orden_id

    @pyqtSlot()
    def request_orden_details(self):
        print(f"BackendBridge: Solicitud de detalles para Orden ID: {self.selected_orden_id_for_view_edit}")
        if self.selected_orden_id_for_view_edit is None:
            error_response = json.dumps({'error_fetch': 'No se seleccionó ninguna orden para ver.'})
            self.ordenDetailsResult.emit(error_response)
            return

        conn = None
        try:
            conn = self.db_manager.connect_db()
            cursor = conn.cursor()
            
            # Query para obtener datos de la orden y datos relacionados (paciente, usuario)
            sql_query = """
                SELECT
                    om.id AS id_orden,
                    om.consulta_id,
                    om.evolucion_id,
                    om.usuario_id AS id_usuario_creador,
                    om.fecha_hora,
                    om.orden_json_blob,
                    om.estado,
                    u_creador.nombre_completo AS nombre_completo_creador_enc,
                    u_creador.nombre_usuario AS username_creador,
                    p.id AS paciente_id_real,
                    p.nombres AS paciente_nombres_enc,
                    p.apellidos AS paciente_apellidos_enc,
                    p.numero_historia AS numero_historia_paciente
                FROM OrdenesMedicas om
                JOIN Usuarios u_creador ON om.usuario_id = u_creador.id
                JOIN Consultas c ON om.consulta_id = c.id
                JOIN Pacientes p ON c.paciente_id = p.id
                WHERE om.id = ?
            """
            cursor.execute(sql_query, (self.selected_orden_id_for_view_edit,))
            row = cursor.fetchone()

            if not row:
                error_response = json.dumps({'error_fetch': f'Orden con ID {self.selected_orden_id_for_view_edit} no encontrada.'})
                self.ordenDetailsResult.emit(error_response)
                return

            # Convertir la fila a un diccionario
            colnames = [desc[0] for desc in cursor.description]
            orden_data = dict(zip(colnames, row))

            # Desencriptar campos necesarios
            try:
                orden_data['usuario_orden_nombre'] = self.db_manager.decrypt_data(orden_data.pop('nombre_completo_creador_enc')) or orden_data.get('username_creador', 'N/D')
            except: orden_data['usuario_orden_nombre'] = orden_data.get('username_creador', '[Err Decrypt]')
            
            try:
                n_pac_dec = self.db_manager.decrypt_data(orden_data.pop('paciente_nombres_enc'))
                a_pac_dec = self.db_manager.decrypt_data(orden_data.pop('paciente_apellidos_enc'))
                orden_data['paciente_nombre_completo'] = f"{n_pac_dec or ''} {a_pac_dec or ''}".strip()
            except: orden_data['paciente_nombre_completo'] = '[Err Decrypt Paciente]'

            # El orden_json_blob ya debería estar como bytes, decrypt_data lo maneja
            # y devuelve un string JSON.
            if orden_data.get('orden_json_blob'):
                try:
                    decrypted_blob_string = self.db_manager.decrypt_data(orden_data['orden_json_blob'])
                    orden_data['orden_json_blob'] = decrypted_blob_string if decrypted_blob_string else "{}"
                except Exception as e_blob:
                    print(f"Error desencriptando orden_json_blob en request_orden_details: {e_blob}")
                    orden_data['orden_json_blob'] = json.dumps({"error_desencriptacion": str(e_blob)})
            else:
                orden_data['orden_json_blob'] = "{}" # String JSON vacío

            # Eliminar username_creador si ya tenemos el nombre completo
            if 'username_creador' in orden_data:
                del orden_data['username_creador']

            print(f"BackendBridge: Detalles de orden ID {self.selected_orden_id_for_view_edit} listos para emitir.")
            self.ordenDetailsResult.emit(json.dumps(orden_data, default=str))

        except sqlite3.Error as db_err:
            print(f"DB Error en request_orden_details: {db_err}")
            traceback.print_exc()
            self.ordenDetailsResult.emit(json.dumps({'error_fetch': f'Error de base de datos: {db_err}'}))
        except Exception as e:
            print(f"Error general en request_orden_details: {e}")
            traceback.print_exc()
            self.ordenDetailsResult.emit(json.dumps({'error_fetch': f'Error inesperado: {e}'}))
        finally:
            if conn:
                conn.close()

    @pyqtSlot(QVariant) # Mantenemos QVariant para flexibilidad, pero verificamos el tipo
    def guardar_nueva_orden_medica(self, orden_data_param): # Renombrado para claridad
        print("BackendBridge: Solicitud guardar_nueva_orden_medica recibida.")
        if not self.current_user_data or 'id' not in self.current_user_data:
            self.ordenMedicaSaveResult.emit(False, "Error: Sesión no válida o usuario no identificado.")
            return
        current_user_id = self.current_user_data['id']

        active_consulta_id = self.current_consulta_id
        if not active_consulta_id and self.selected_patient_id:
            print("BackendBridge: No había current_consulta_id, intentando obtener la más reciente...")
            active_consulta_id = self.patient_actions.get_latest_consulta_id_for_patient(self.selected_patient_id)
        
        if not active_consulta_id:
            self.ordenMedicaSaveResult.emit(False, "Error: No se pudo determinar la consulta activa para asociar la orden.")
            return
        
        print(f"BackendBridge: Guardando orden para Paciente ID: {self.selected_patient_id}, Consulta ID: {active_consulta_id}, Usuario ID: {current_user_id}")

        try:
            orden_data_json_obj = None
            if isinstance(orden_data_param, dict):
                print("BackendBridge: orden_data_param ya es un diccionario Python.")
                orden_data_json_obj = orden_data_param
            elif isinstance(orden_data_param, QVariant):
                print("BackendBridge: orden_data_param es QVariant, convirtiendo a dict...")
                orden_data_json_obj = orden_data_param.toVariant()
                if not isinstance(orden_data_json_obj, dict):
                    # Intento adicional si toVariant() no dio un dict directamente
                    try:
                        orden_data_json_obj = orden_data_param.toJsonObject().toVariantMap()
                    except AttributeError:
                        pass # Dejar que la siguiente validación falle si no es dict
            else:
                raise TypeError(f"Tipo de dato inesperado para orden_data_param: {type(orden_data_param)}")

            if not isinstance(orden_data_json_obj, dict):
                 raise TypeError("Los datos de la orden no son un diccionario Python válido después de la conversión.")
            
            print(f"BackendBridge: Datos de orden listos (primeras claves): {list(orden_data_json_obj.keys())[:5]}")

            json_string_to_encrypt = json.dumps(orden_data_json_obj)
            encrypted_orden_json_blob = self.db_manager.encrypt_data(json_string_to_encrypt)

            conn = self.db_manager.connect_db()
            with conn:
                cursor = conn.cursor()
                sql = """
                    INSERT INTO OrdenesMedicas
                    (consulta_id, usuario_id, orden_json_blob, estado)
                    VALUES (?, ?, ?, ?)
                """
                cursor.execute(sql, (
                    active_consulta_id,
                    current_user_id,
                    encrypted_orden_json_blob,
                    'Pendiente'
                ))
                orden_id = cursor.lastrowid
                self.db_manager.log_action(
                    conn, current_user_id, 'CREAR_ORDEN_MEDICA',
                    f"Orden médica ID {orden_id} creada para Paciente ID {self.selected_patient_id}, Consulta ID {active_consulta_id}",
                    tabla='OrdenesMedicas', registro_id=orden_id,
                    detalles={'paciente_id': self.selected_patient_id, 'consulta_id': active_consulta_id}
                )
            self.ordenMedicaSaveResult.emit(True, f'Órdenes médicas guardadas exitosamente (ID: {orden_id}).')
            print(f"BackendBridge: Orden médica {orden_id} guardada para consulta {active_consulta_id}")

        except TypeError as te:
            print(f"BackendBridge ERROR (guardar_nueva_orden_medica - TypeError): {te}")
            traceback.print_exc()
            self.ordenMedicaSaveResult.emit(False, f"Error interno procesando datos de orden: {te}")
        except Exception as e:
            print(f"BackendBridge ERROR al guardar orden médica: {e}")
            traceback.print_exc()
            self.ordenMedicaSaveResult.emit(False, f'Error al guardar las órdenes: {str(e)}')


    def _convert_qvariant_to_dict(self, qvariant_data, context_str="datos"):
        """Convierte QVariant a dict, manejando posibles errores."""
        data_dict = None
        if isinstance(qvariant_data, QVariant):
            data_dict = qvariant_data.toVariant() # Intento primario
            if not isinstance(data_dict, dict): # Si el primario no dio dict
                try: 
                    # Intento secundario para casos donde toVariant() devuelve algo más
                    data_dict = qvariant_data.toJsonObject().toVariantMap() 
                except AttributeError: 
                    # Si no tiene esos métodos, toJsonObject o toVariantMap
                    pass # data_dict sigue siendo lo que era
        elif isinstance(qvariant_data, dict):
            data_dict = qvariant_data # Ya es un dict
        
        # Verificar el resultado final
        if not isinstance(data_dict, dict):
            error_msg = f"La conversión de {context_str} no resultó en un diccionario (obtenido: {type(data_dict)})."
            print(f"--- BackendBridge ERROR: {error_msg}")
            # Lanzar una excepción que será capturada por el slot que la llamó
            raise TypeError(error_msg) 
        return data_dict

    def get_absolute_path(self, relative_path):
         return os.path.join(self.get_base_path(), relative_path)
    
    def _process_and_save_photo(self, medico_data_dict_ref):
        """
        Procesa 'foto_base64' si existe en medico_data_dict_ref.
        Guarda la foto y devuelve su ruta relativa.
        MODIFICA medico_data_dict_ref eliminando 'foto_base64'.
        Devuelve la ruta de la foto guardada o None si no se procesó nueva foto.
        """
        print("--- _process_and_save_photo: Iniciando ---")
        foto_base64 = medico_data_dict_ref.pop('foto_base64', None)

        if not foto_base64:
            print("--- _process_and_save_photo: No se recibió foto_base64. No se procesará nueva foto.")
            return None # Indica que no se procesó una nueva foto

        print(f"--- _process_and_save_photo: Recibida foto_base64 (primeros 80 chars): {str(foto_base64)[:80]}...")
        
        try:
            if not isinstance(foto_base64, str) or not foto_base64.startswith('data:image/') or ',' not in foto_base64:
                raise ValueError("Formato de foto base64 inválido (sin cabecera data:image/ o separador ',').")

            header, encoded_data = foto_base64.split(',', 1)
            image_data_bytes = base64.b64decode(encoded_data)
            
            mime_type = header.split(';')[0].split(':')[1].lower()
            file_ext = None
            if mime_type == "image/png": file_ext = ".png"
            elif mime_type in ["image/jpeg", "image/jpg"]: file_ext = ".jpg"
            else: raise ValueError(f"Formato de imagen no soportado ({mime_type}). Solo JPG/PNG.")

            photo_dir_name = "user_photos"
            photo_dir_abs = self.get_absolute_path(photo_dir_name)
            os.makedirs(photo_dir_abs, exist_ok=True)
            
            unique_filename = f"user_{uuid.uuid4().hex}{file_ext}"
            filepath_abs = os.path.join(photo_dir_abs, unique_filename)
            filepath_relative = os.path.join(photo_dir_name, unique_filename).replace('\\', '/')
            
            with open(filepath_abs, "wb") as f:
                f.write(image_data_bytes)
            print(f"--- _process_and_save_photo: Foto guardada exitosamente en: {filepath_relative}")
            return filepath_relative

        except Exception as e:
            print(f"--- _process_and_save_photo ERROR (Procesando/Guardando foto): {e}")
            traceback.print_exc()
            # No relanzar aquí, la función principal decidirá qué hacer con el None devuelto.
            return None # Indica fallo al procesar la nueva foto
    # --- Slots expuestos a JavaScript ---

    @pyqtSlot(str)
    def handle_print_request(self, html_content):
        print(f"BackendBridge: Recibida solicitud de impresión con HTML (longitud: {len(html_content)})")

        # Opción a: Usar QPrinter y QTextDocument (para HTML simple a moderado)
        try:
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            printDialog = QPrintDialog(printer, self.parent_window) # self.parent_window es tu QMainWindow

            if printDialog.exec() == QPrintDialog.DialogCode.Accepted:
                doc = QTextDocument()
                doc.setHtml(html_content)
                # Escalar para ajustar al tamaño de página si es necesario, esto es un ejemplo simple
                # podrías necesitar ajustar márgenes, etc.
                # doc.setPageSize(printer.pageRect(QPrinter.Unit.DevicePixel).size())
                doc.print(printer)
                print("BackendBridge: Documento enviado a la impresora.")
            else:
                print("BackendBridge: Diálogo de impresión cancelado por el usuario.")

        except Exception as e:
            print(f"BackendBridge ERROR al imprimir con QPrinter/QTextDocument: {e}")
            traceback.print_exc()

    @pyqtSlot(str, str)
    def attempt_login(self, username, password):
        print(f"BackendBridge: Recibido intento de login para usuario: {username}")
        user_data = auth.verify_user_login(username, password)
        
        if user_data:
            print(f"BackendBridge: Login exitoso para: {user_data.get('username')}")
            self.current_user_data = user_data

            # --- Registrar acción de LOGIN EXITOSO ---
            conn_log = None
            try:
                logged_in_user_id = user_data.get('id')
                if logged_in_user_id is not None:
                    conn_log = database.connect_db()
                    if conn_log:
                        descripcion = f"Inicio de sesión exitoso para el usuario: {user_data.get('username', 'Desconocido')}."
                        database.log_action(
                            db_conn=conn_log,
                            usuario_id=logged_in_user_id,
                            tipo_accion="LOGIN_EXITOSO",
                            descripcion=descripcion,
                            # ***** CORRECCIÓN DE NOMBRES DE ARGUMENTOS AQUÍ *****
                            tabla=None,                 # Antes era tabla_afectada
                            registro_id=None,           # Antes era registro_afectado_id
                            detalles={'username': user_data.get('username')} # 'detalles' ya era correcto
                        )
                        conn_log.commit() 
                        print(f"BackendBridge: Acción de login para user_id {logged_in_user_id} registrada.")
                    # ... (resto del try-except-finally como antes) ...
            except sqlite3.Error as e_sql:
                print(f"BackendBridge: Error de SQLite al registrar log de login: {e_sql}")
                if conn_log:
                    conn_log.rollback() 
                traceback.print_exc()
            except Exception as e:
                print(f"BackendBridge: Error general al registrar log de login: {e}")
                if conn_log:
                    conn_log.rollback()
                traceback.print_exc()
            finally:
                if conn_log:
                    conn_log.close()
            # --- Fin de registrar acción ---

            self.login_success.emit(user_data)
        else:
            print("BackendBridge: Login fallido.")
            # --- Registrar acción de LOGIN FALLIDO ---
            conn_log_fail = None
            try:
                conn_log_fail = database.connect_db()
                if conn_log_fail:
                    descripcion_fallo = f"Intento de login fallido para el nombre de usuario: {username}."
                    database.log_action(
                        db_conn=conn_log_fail,
                        usuario_id=0, 
                        tipo_accion="LOGIN_FALLIDO",
                        descripcion=descripcion_fallo,
                        # ***** CORRECCIÓN DE NOMBRES DE ARGUMENTOS AQUÍ *****
                        tabla=None,                 # Si no aplica, puedes omitirlo ya que tiene default
                        registro_id=None,           # Si no aplica, puedes omitirlo ya que tiene default
                        detalles={'username_intentado': username}
                    )
                    conn_log_fail.commit()
                    print(f"BackendBridge: Acción de login fallido para '{username}' registrada.")
                # ... (resto del try-except-finally como antes) ...
            except Exception as e_fail:
                print(f"BackendBridge: Error al registrar log de login fallido: {e_fail}")
                if conn_log_fail:
                    conn_log_fail.rollback()
            finally:
                if conn_log_fail:
                    conn_log_fail.close()
            # --- Fin de registrar acción de LOGIN FALLIDO ---
            self.login_failed.emit("Usuario o contraseña incorrectos.")

    @pyqtSlot()
    def request_initial_data(self):
        print("BackendBridge: Solicitud de datos iniciales.")
        
        # Paso 1: Emitir los datos del usuario para la barra lateral
        username_to_send = 'No Autenticado' 
        patient_count_to_send = 0 # O cualquier otro dato que el dashboard pueda necesitar directamente

        if self.current_user_data:
            # ... (lógica para obtener username_to_send y patient_count_to_send como antes) ...
            temp_username = self.current_user_data.get('username')
            if temp_username and isinstance(temp_username, str) and temp_username.strip():
                username_to_send = temp_username
            else:
                username_to_send = "Usuario (Inválido)"
            
            try:
                if hasattr(self.patient_manager, 'get_count'): # Ejemplo
                    patient_count_to_send = self.patient_manager.get_count()
            except Exception as e_count:
                patient_count_to_send = 'Err'
        
        initial_user_info = {
            'username': username_to_send,
            'patientCount': patient_count_to_send # Dashboard podría usar esto
        }
        print(f"BackendBridge: Emitiendo userDataLoaded con: {initial_user_info}")
        self.userDataLoaded.emit(QVariant(initial_user_info)) # Asumiendo que QVariant funcionó

        # Paso 2: Solicitar que se cargue la vista del dashboard
        # La función loadContent en JS ya pone "Cargando..."
        print("BackendBridge: Solicitando carga de la vista 'dashboard'.")
        self.request_view_content("dashboard")

    @pyqtSlot(str)
    def request_view_content(self, view_name_with_separator): # Renombrado para claridad
        print(f"BackendBridge: Solicitud recibida para vista: '{view_name_with_separator}'")

        # Usaremos '__' como separador para indicar subdirectorios.
        # Ejemplo: 'historial__historial_acciones' se convertirá en la ruta 'historial/historial_acciones.html'
        # Ejemplo: 'dashboard' se convertirá en 'dashboard.html' (en la raíz de html_files)

        path_parts_from_view_name = view_name_with_separator.split('__')
        
        sane_path_components = []
        for part in path_parts_from_view_name:
            # Sanear cada parte: permitir alfanuméricos y guion bajo.
            # Esta sanitización es por cada componente del path, no para el string completo.
            sane_component = "".join(c for c in part if c.isalnum() or c == '_')
            if not sane_component or sane_component != part:
                error_message = f"Componente de nombre de vista inválido ('{part}') en '{view_name_with_separator}'."
                print(f"BackendBridge Error: {error_message}")
                error_html = f"<p style='color:red;'>Error: {error_message}</p>"
                self.viewContentLoaded.emit(error_html, "error") # Emitir 'error' como segundo argumento
                return
            sane_path_components.append(sane_component)

        if not sane_path_components:
            error_message = f"Nombre de vista inválido o vacío después del procesamiento: '{view_name_with_separator}'."
            print(f"BackendBridge Error: {error_message}")
            error_html = f"<p style='color:red;'>Error: {error_message}</p>"
            self.viewContentLoaded.emit(error_html, "error")
            return

        # Construir la ruta relativa del fragmento dentro de 'html_files'
        # Ejemplo: ['historial', 'historial_acciones'] -> 'historial/historial_acciones.html'
        # Ejemplo: ['dashboard'] -> 'dashboard.html'
        relative_fragment_path = os.path.join(*sane_path_components) + ".html"
        
        try:
            # get_absolute_path ya espera una ruta relativa a la raíz del proyecto.
            # os.path.join("html_files", ...) construye la ruta relativa completa desde la raíz del proyecto.
            target_file_path = self.get_absolute_path(os.path.join("html_files", relative_fragment_path))
            
            print(f"BackendBridge: Intentando leer archivo fragmento: {target_file_path}")

            # Verificación de seguridad adicional (aunque get_absolute_path y os.path.join deberían manejarlo bien
            # si get_base_path es seguro y los componentes son saneados).
            # Nos aseguramos de que el path resuelto esté dentro del directorio 'html_files' esperado.
            base_html_dir_abs = os.path.abspath(self.get_absolute_path("html_files"))
            target_file_path_abs = os.path.abspath(target_file_path)

            if not target_file_path_abs.startswith(base_html_dir_abs + os.sep) and target_file_path_abs != base_html_dir_abs : # os.sep para el separador correcto. Añadida condición por si base_html_dir_abs es el archivo mismo (poco probable aqui)
                print(f"BackendBridge Error: Intento de Path Traversal o ruta fuera de 'html_files' para '{view_name_with_separator}'. Path resuelto: '{target_file_path_abs}', Base esperada: '{base_html_dir_abs}'")
                error_html = f"<p style='color:red;'>Error de seguridad al cargar la vista.</p>"
                self.viewContentLoaded.emit(error_html, "error_security") # Usar un tipo de error específico
                return

            if os.path.exists(target_file_path) and os.path.isfile(target_file_path):
                with open(target_file_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                print(f"BackendBridge: Contenido de '{relative_fragment_path}' leído. Enviando a JS...")
                # Usar el view_name_with_separator original para la señal,
                # ya que JS podría usarlo para identificar la vista cargada.
                self.viewContentLoaded.emit(html_content, view_name_with_separator)
            else:
                error_message = f"Archivo fragmento NO encontrado o no es un archivo: {target_file_path}"
                print(f"BackendBridge Error: {error_message}")
                error_html = f"<p style='color:red;'>Error: No se pudo cargar la vista '{view_name_with_separator}'. Archivo no encontrado.</p>"
                self.viewContentLoaded.emit(error_html, "error_not_found") # Usar un tipo de error específico
        except Exception as e:
            print(f"BackendBridge Error: Excepción al leer '{relative_fragment_path}':")
            traceback.print_exc()
            error_html = f"<p style='color:red;'>Error interno al cargar la vista '{view_name_with_separator}'.</p>"
            self.viewContentLoaded.emit(error_html, "error_internal") # Usar un tipo de error específico

    @pyqtSlot(QVariant)
    def save_new_patient(self, patient_data_qvariant):
        """Recibe datos de JS, convierte y delega el guardado."""
        print("BackendBridge: Recibida solicitud para guardar nuevo paciente...")
        patient_data = None # Asegurar que patient_data esté definido
        try:
            if isinstance(patient_data_qvariant, QVariant):
                 patient_data = patient_data_qvariant.toVariant()
                 if not isinstance(patient_data, dict):
                      # Intento adicional para ciertos tipos de QVariant que podrían ser objetos JSON
                      try: patient_data = patient_data_qvariant.toJsonObject().toVariantMap()
                      except AttributeError: # Si no tiene toJsonObject o toVariantMap
                           raise TypeError("No se pudo convertir QVariant a dict (paso intermedio falló).")
            elif isinstance(patient_data_qvariant, dict): # Ya es un dict
                 patient_data = patient_data_qvariant
            else: # Tipo no esperado
                 raise TypeError(f"Tipo inesperado recibido para datos de paciente: {type(patient_data_qvariant)}")

            # Verificar si la conversión resultó en un dict
            if not isinstance(patient_data, dict):
                raise TypeError(f"La conversión de datos del paciente no resultó en un diccionario (obtenido: {type(patient_data)}).")

            print(f"BackendBridge: Datos convertidos a dict Python: {list(patient_data.keys())}")
        except Exception as e:
            print(f"BackendBridge ERROR: Fallo en conversión de datos del paciente: {e}")
            traceback.print_exc()
            self.patientSaveResult.emit(False, f"Error interno al procesar datos: {e}", None)
            return

        if not self.current_user_data or 'id' not in self.current_user_data:
            print("BackendBridge Error: Usuario no autenticado o falta ID de usuario.")
            self.patientSaveResult.emit(False, "Error: Sesión no válida o usuario no identificado.", None)
            return

        current_user_id = self.current_user_data['id']
        success, message, new_historia = self.patient_manager.save_new(patient_data, current_user_id)
        print(f"BackendBridge: Resultado guardado: {success}, msg='{message}', historia='{new_historia}'")
        self.patientSaveResult.emit(success, message, new_historia)

    @pyqtSlot()
    def get_next_historia_number(self):
        """Obtiene y formatea el próximo N° de Historia potencial."""
        print("BackendBridge: Solicitud para próximo N° Historia recibida.")
        conn = None
        next_historia_str = None # Renombrado para evitar confusión con el N° Historia
        try:
            conn = database.connect_db()
            if conn:
                cursor = conn.cursor()
                # Usa la lógica movida a PatientActions
                # Asegúrate que _get_next_patient_id y _format_historia_numero sean accesibles
                # o que haya un método público en PatientActions que haga esto.
                # Por simplicidad, asumiré que puedes llamar a métodos "privados" aquí
                # pero sería mejor un método público en PatientActions.
                next_id = self.patient_manager._get_next_patient_id(cursor)
                next_historia_str = self.patient_manager._format_historia_numero(next_id)
                cursor.close()
            else:
                 print("BackendBridge Error: No se pudo conectar a BD para obtener next ID.")
        except Exception as e:
            print(f"BackendBridge Error obteniendo próximo N° Historia: {e}")
            traceback.print_exc()
        finally:
            if conn: conn.close()

        if next_historia_str:
            print(f"BackendBridge: Enviando próximo N° Historia: {next_historia_str}")
            self.nextHistoriaReady.emit(next_historia_str)
        else:
            print("BackendBridge: No se pudo determinar próximo N° Historia.")
            self.nextHistoriaReady.emit("(Error)")
    
    @pyqtSlot(str)
    def request_patient_list(self, search_term=''):
        print(f"BackendBridge: Solicitud recibida para lista COMPLETA. Búsqueda: '{search_term}'")
        try:
            patients, total_count = self.patient_manager.get_list(search_term=search_term)
            if patients is None:
                 print("BackendBridge Error: patient_manager.get_list devolvió error.")
                 self.patientListResult.emit([], 0)
            else:
                 print(f"BackendBridge: Enviando {len(patients)} pacientes (Total: {total_count})")
                 self.patientListResult.emit(patients, total_count)
        except Exception as e:
            print(f"BackendBridge Error: Excepción al obtener lista de pacientes: {e}")
            traceback.print_exc()
            self.patientListResult.emit([], 0)

    @pyqtSlot()
    def request_action_log(self):
        print(f"BackendBridge: Solicitud recibida para historial de acciones.")
        try:
            logs, total_count = self.historial_manager.get_log()
            if logs is None:
                 print("BackendBridge Error: historial_manager.get_log devolvió error.")
                 self.actionLogResult.emit([], 0)
            else:
                 print(f"BackendBridge: Enviando {len(logs)} entradas de log (Total: {total_count})")
                 self.actionLogResult.emit(logs, total_count)
        except Exception as e:
            print(f"BackendBridge Error: Excepción al obtener historial: {e}")
            traceback.print_exc()
            self.actionLogResult.emit([], 0)

    @pyqtSlot()
    def request_medico_list(self):
        print("BackendBridge: Solicitud recibida para lista de médicos/usuarios.")
        try:
            medicos, total_count = self.medico_manager.get_list()
            if medicos is None:
                 self.medicoListResult.emit([], 0)
            else:
                 print(f"BackendBridge: Enviando {len(medicos)} médicos/usuarios.")
                 self.medicoListResult.emit(medicos, total_count)
        except Exception as e:
            print(f"BackendBridge Error obteniendo lista médicos: {e}"); traceback.print_exc()
            self.medicoListResult.emit([], 0)

    @pyqtSlot(QVariant)
    def add_new_medico(self, medico_data_qvariant):
        print("BackendBridge: Solicitud para guardar nuevo médico/usuario...")
        if not self.current_user_data or 'id' not in self.current_user_data:
            self.medicoAddResult.emit(False, "Error: Sesión no válida."); return
        current_user_id = self.current_user_data['id']
        
        medico_data = None
        try: # Conversión QVariant a dict
            if isinstance(medico_data_qvariant, QVariant):
                medico_data = medico_data_qvariant.toVariant()
                if not isinstance(medico_data, dict):
                    try: medico_data = medico_data_qvariant.toJsonObject().toVariantMap()
                    except AttributeError: raise TypeError("Conv QVariant (medico) falló")
            elif isinstance(medico_data_qvariant, dict): medico_data = medico_data_qvariant
            else: raise TypeError(f"Tipo inesperado: {type(medico_data_qvariant)}")
            if not isinstance(medico_data, dict): raise TypeError("Conversión no resultó en dict")
        except Exception as e:
            print(f"Error conversión datos médico: {e}"); traceback.print_exc()
            self.medicoAddResult.emit(False, "Error interno procesando datos."); return

        # Procesar y guardar la foto (si existe en base64) y obtener la ruta
        try:
            ruta_foto_guardada = self._process_and_save_photo(medico_data) # Modifica medico_data quitando foto_base64
            medico_data['ruta_foto_perfil'] = ruta_foto_guardada # Añadir/Actualizar la ruta en los datos a guardar
        except Exception as e_proc:
            print(f"Error procesando foto durante ADD: {e_proc}")
            # Decidir si continuar sin foto o emitir error
            self.medicoAddResult.emit(False, f"Error procesando foto: {e_proc}"); return

        # Llamar a la lógica de negocio para añadir el usuario con la ruta de foto actualizada
        success, message = self.medico_manager.add_new(medico_data, current_user_id)
        print(f"BackendBridge: Resultado add médico: {success}, {message}")
        self.medicoAddResult.emit(success, message)

    @pyqtSlot(int)
    def set_selected_patient(self, patient_id):
        print(f"BackendBridge: set_selected_patient ID: {patient_id}")
        try:
            self.selected_patient_id = int(patient_id)
        except (ValueError, TypeError):
            print(f"WARN: set_selected_patient ID inválido: {patient_id}")
            self.selected_patient_id = None

    @pyqtSlot()
    def request_patient_info_for_add_evolucion(self):
        """Solicita la info básica del paciente actualmente seleccionado."""
        print("BackendBridge: Recibida solicitud de info básica para 'Agregar Evolución'")
        if self.selected_patient_id:
            print(f"BackendBridge: Buscando info para ID: {self.selected_patient_id}")
            basic_info = self.patient_actions.get_patient_basic_info(self.selected_patient_id)
            # Convertir fechas/datetimes si las hubiera (aunque aquí no hay)
            json_data = json.dumps(basic_info, default=str)
            print(f"BackendBridge: Enviando info básica: {json_data}")
            self.sendPatientInfoForAddEvolucion.emit(json_data)
        else:
            print("BackendBridge Error: No hay paciente seleccionado para obtener info básica.")
            error_info = {"error": "No hay paciente seleccionado en el backend."}
            self.sendPatientInfoForAddEvolucion.emit(json.dumps(error_info))

    @pyqtSlot(QVariant)
    def update_patient_basic_data(self, patient_data_qvariant):
        print(f"--- BackendBridge: Recibida solicitud update_patient_basic_data ---")
        
        # 1. Verificar usuario actual
        if not self.current_user_data or 'id' not in self.current_user_data:
            self.updatePatientBasicDataResult.emit(False, "Error: Sesión no válida o usuario no identificado.")
            return
        current_user_id = self.current_user_data['id']

        # 2. Convertir QVariant a diccionario Python
        try:
            patient_data_dict = self._convert_qvariant_to_dict(patient_data_qvariant, "datos básicos del paciente")
            print(f"--- BackendBridge: Datos convertidos: {list(patient_data_dict.keys())}")
        except TypeError as te:
            print(f"BackendBridge ERROR (update_patient_basic_data - TypeError): {te}")
            self.updatePatientBasicDataResult.emit(False, f"Error interno procesando datos: {te}")
            return
        except Exception as e_conv:
             print(f"BackendBridge ERROR (update_patient_basic_data - Conversión): {e_conv}")
             traceback.print_exc()
             self.updatePatientBasicDataResult.emit(False, f"Error inesperado al procesar datos: {e_conv}")
             return

        # 3. Obtener el ID del paciente (viene en el diccionario del formulario)
        patient_id_to_update = patient_data_dict.get('id')
        if not patient_id_to_update or not isinstance(patient_id_to_update, (str, int)) or int(patient_id_to_update) <= 0:
             # Intentar obtenerlo del estado guardado como fallback (aunque no debería ser necesario)
             patient_id_to_update = self.selected_patient_id
             if not patient_id_to_update or not isinstance(patient_id_to_update, int) or patient_id_to_update <= 0:
                 print(f"--- BackendBridge ERROR: ID de paciente inválido o faltante en update_patient_basic_data. Datos recibidos: {patient_data_dict}, ID guardado: {self.selected_patient_id}")
                 self.updatePatientBasicDataResult.emit(False, "Error: No se pudo identificar al paciente para actualizar.")
                 return
        else:
            # Asegurar que sea un entero
            try:
                patient_id_to_update = int(patient_id_to_update)
            except ValueError:
                 print(f"--- BackendBridge ERROR: ID de paciente no es un número válido: {patient_data_dict.get('id')}")
                 self.updatePatientBasicDataResult.emit(False, "Error: Identificador de paciente inválido.")
                 return


        # 4. Llamar a la lógica de negocio en PacienteActions
        try:
            # Pasar el diccionario completo y el ID del usuario que realiza la acción
            success, message = self.patient_manager.update_basic_data(patient_data_dict, current_user_id)
            print(f"--- BackendBridge: Resultado update_basic_data desde PacienteActions: {success}, '{message}' ---")
            self.updatePatientBasicDataResult.emit(success, message) # Emitir resultado al frontend
        except AttributeError:
            print("--- BackendBridge ERROR: PacienteActions no tiene el método 'update_basic_data'. ---")
            self.updatePatientBasicDataResult.emit(False, "Error interno del servidor (función de actualización no encontrada).")
        except Exception as e:
            print(f"--- BackendBridge ERROR: Excepción en update_patient_basic_data llamando a PacienteActions: {e} ---")
            traceback.print_exc()
            self.updatePatientBasicDataResult.emit(False, f"Error inesperado al guardar cambios: {e}")

    @pyqtSlot()
    def request_patient_details(self):
        print(f"BackendBridge: Solicitud detalles paciente ID: {self.selected_patient_id}")
        if self.selected_patient_id is None:
            print("BackendBridge Error: No hay paciente seleccionado.")
            self.patientDetailsResult.emit(json.dumps({'error': 'No se seleccionó paciente'}))
            return

        details = None
        try:
            # Llama a patient_manager.get_details, que debería devolver un dict
            # ya con todos los campos desencriptados y listos para ser serializados.
            details = self.patient_manager.get_details(self.selected_patient_id)

            if details is None or details.get("error"): # Si get_details devuelve None o un dict con error
                error_msg = details.get("error") if isinstance(details, dict) else "No se encontraron detalles del paciente."
                print(f"BackendBridge: get_details devolvió error o None: {error_msg}")
                self.patientDetailsResult.emit(json.dumps({'error': error_msg}))
                return

            # ---- INICIO DE LA SECCIÓN CRÍTICA PARA ÓRDENES ----
            # Ahora, 'details' ya tiene 'ordenes_medicas_todas'
            # Vamos a verificar y asegurar que 'orden_json_blob' en cada orden sea un STRING JSON
            # Esta verificación es más para depuración, PatientActions.get_details debería haberlo hecho.

            if 'ordenes_medicas_todas' in details and details['ordenes_medicas_todas']:
                for orden_item in details['ordenes_medicas_todas']:
                    if 'orden_json_blob' in orden_item:
                        blob_content = orden_item['orden_json_blob']
                        if isinstance(blob_content, bytes):
                            # ESTO NO DEBERÍA SUCEDER SI PatientActions.get_details lo hizo bien
                            print(f"WARN: orden_json_blob (ID: {orden_item.get('id')}) sigue siendo bytes en BackendBridge. Intentando desencriptar aquí.")
                            try:
                                decrypted_str = self.db_manager.decrypt_data(blob_content)
                                orden_item['orden_json_blob'] = decrypted_str if decrypted_str else "{}"
                            except Exception as e_dec_bridge:
                                print(f"ERROR en BackendBridge al intentar desencriptar blob tardíamente: {e_dec_bridge}")
                                orden_item['orden_json_blob'] = json.dumps({"error_desencriptacion_tardia": str(e_dec_bridge)})
                        elif not isinstance(blob_content, str):
                             # Si no es string ni bytes (ej. ya es un dict parseado), convertirlo a string JSON
                             print(f"WARN: orden_json_blob (ID: {orden_item.get('id')}) no es string. Convirtiendo a string JSON.")
                             try:
                                 orden_item['orden_json_blob'] = json.dumps(blob_content)
                             except Exception as e_dump_bridge:
                                 print(f"ERROR en BackendBridge al intentar json.dumps de blob no string: {e_dump_bridge}")
                                 orden_item['orden_json_blob'] = json.dumps({"error_conversion_a_string_json": str(e_dump_bridge)})
                        # Si ya es un string, se asume que es el string JSON correcto.
            # ---- FIN DE LA SECCIÓN CRÍTICA PARA ÓRDENES ----


            # Guardar el ID de la consulta más reciente si existe
            if 'consultas_info' in details and details['consultas_info']:
                self.current_consulta_id = details['consultas_info'][0].get('id')
                print(f"BackendBridge: Consulta actual establecida a ID: {self.current_consulta_id} para Paciente ID: {self.selected_patient_id}")
            else:
                self.current_consulta_id = None
                print(f"BackendBridge: No se pudo establecer consulta actual para Paciente ID: {self.selected_patient_id}.")


            # Serializar el diccionario 'details' completo a un string JSON
            print(f"BackendBridge: Serializando detalles del paciente a JSON...")
            json_string = json.dumps(details, default=str) # default=str para manejar tipos no serializables
            print(f"BackendBridge: Emitiendo detalles JSON (primeros 500 chars): {json_string[:500]}...")
            self.patientDetailsResult.emit(json_string)

        except Exception as e:
            print(f"BackendBridge Error: Excepción al obtener/procesar detalles: {e}")
            traceback.print_exc()
            self.patientDetailsResult.emit(json.dumps({'error': f'Error interno: {e}'}))

    @pyqtSlot(int)
    def set_selected_medico_for_edit(self, medico_id):
        print(f"BackendBridge: Médico seleccionado para editar ID: {medico_id}")
        print(f"--- SETTING selected_medico_id_to_edit: ID={medico_id} (Tipo: {type(medico_id)}) ---")
        self.selected_medico_id_to_edit = medico_id

    @pyqtSlot() # Sigue emitiendo señal, no devuelve resultado directo
    def get_ing_test(self): # O renómbralo a request_ingreso_details si pruebas
        # El nombre que uses aquí debe coincidir con la llamada en JavaScript
        print(f"PYTHON: {self.get_ing_test.__name__} (CON LÓGICA REAL) FUE LLAMADO") # Usar __name__ para que el log se actualice si renombras
        print(f"  Usando patient_id: {self.selected_patient_id}, consulta_id: {self.selected_consulta_id_for_edit}")

        if not self.selected_patient_id or not self.selected_consulta_id_for_edit:
            error_msg = "No se ha seleccionado un paciente o una consulta válidos para editar."
            print(f"PYTHON Error en {self.get_ing_test.__name__}: {error_msg}")
            self.ingresoDetailsResult.emit(json.dumps({"error": error_msg}))
            return
        
        try:
            # LLAMADA A LA LÓGICA REAL
            ingreso_data = self.patient_manager.get_ingreso_details(
                self.selected_patient_id, 
                self.selected_consulta_id_for_edit
            )
            
            if ingreso_data and not ingreso_data.get("error"):
                print(f"PYTHON ({self.get_ing_test.__name__}): Detalles de ingreso obtenidos de patient_manager. Emitiendo...")
                self.ingresoDetailsResult.emit(json.dumps(ingreso_data, default=str)) # default=str por si hay fechas u otros tipos
            else:
                error_detail = ingreso_data.get("error", "No se pudieron obtener los datos de ingreso desde patient_manager.")
                print(f"PYTHON Error en {self.get_ing_test.__name__}: {error_detail}")
                self.ingresoDetailsResult.emit(json.dumps({"error": error_detail}))
        except AttributeError as ae:
            # Esto podría pasar si patient_manager no está instanciado o no tiene get_ingreso_details
            print(f"PYTHON Error (AttributeError) en {self.get_ing_test.__name__}: {ae}")
            traceback.print_exc()
            self.ingresoDetailsResult.emit(json.dumps({"error": f"Error interno del servidor (atributo): {str(ae)}"}))
        except Exception as e:
            print(f"PYTHON Error (Excepción general) en {self.get_ing_test.__name__}: {e}")
            traceback.print_exc()
            self.ingresoDetailsResult.emit(json.dumps({"error": f"Error interno obteniendo datos de ingreso: {str(e)}"}))

        
    # --- NUEVO SLOT para solicitar detalles del médico ---
    @pyqtSlot()
    def request_medico_details(self):
        print(f"BackendBridge: Solicitud detalles médico ID: {self.selected_medico_id_to_edit}")
        # (Verificación de ID como antes)
        if self.selected_medico_id_to_edit is None:
            # Emitir error como JSON string también
            error_msg = json.dumps({'error': 'No se seleccionó médico para editar'})
            self.medicoDetailsResult.emit(error_msg)
            return

        details = None
        try:
            details = self.medico_manager.get_details(self.selected_medico_id_to_edit)
            print(f"DEBUG: Detalles obtenidos de MedicoActions: {details}")

            if details is None:
                print(f"DEBUG: Emitiendo medicoDetailsResult con error (None) como JSON string.")
                error_msg = json.dumps({'error': 'No se encontraron detalles del médico.'})
                self.medicoDetailsResult.emit(error_msg)
            elif isinstance(details, dict):
                # ***** 2. SERIALIZAR A JSON ANTES DE EMITIR *****
                json_string = ""
                try:
                    # Usar default=str por si acaso hay tipos no serializables por defecto (aunque get_details ya debería limpiarlos)
                    json_string = json.dumps(details, default=str) 
                    print(f"DEBUG: Emitiendo medicoDetailsResult como JSON string (primeros 200 chars): {json_string[:200]}")
                    self.medicoDetailsResult.emit(json_string) # Emitir el string
                except Exception as json_e:
                    print(f"!!!!!!!!!! ERROR CRÍTICO: Fallo al serializar detalles a JSON antes de emitir: {json_e} !!!!!!!!!!")
                    traceback.print_exc()
                    error_msg = json.dumps({'error': f'Error interno de serialización: {json_e}'})
                    self.medicoDetailsResult.emit(error_msg)
            else:
                # Si get_details devuelve algo que no es ni dict ni None
                print(f"DEBUG: Emitiendo medicoDetailsResult con error (Tipo inesperado) como JSON string.")
                error_msg = json.dumps({'error': f'Error interno: tipo de datos inesperado ({type(details).__name__})'})
                self.medicoDetailsResult.emit(error_msg)

        except Exception as e:
            print(f"BackendBridge Error: Excepción general al obtener/procesar detalles: {e}")
            traceback.print_exc()
            error_msg = json.dumps({'error': f'Error interno general: {e}'})
            self.medicoDetailsResult.emit(error_msg)
        # finally: (sin cambios)
        #     pass

    # --- NUEVO SLOT para actualizar médico ---
    @pyqtSlot(int, QVariant)
    def update_medico(self, medico_id, medico_data_qvariant):
        """Recibe datos del form JS, convierte, procesa foto y delega la actualización."""
        print(f"BackendBridge: Solicitud para ACTUALIZAR médico ID: {medico_id}...")
        if not self.current_user_data or 'id' not in self.current_user_data:
            self.medicoUpdateResult.emit(False, "Error: Sesión no válida."); return
        current_user_id = self.current_user_data['id']

        medico_data = None
        try: # Conversión QVariant a dict
            if isinstance(medico_data_qvariant, QVariant):
                medico_data = medico_data_qvariant.toVariant()
                if not isinstance(medico_data, dict):
                    try: medico_data = medico_data_qvariant.toJsonObject().toVariantMap()
                    except AttributeError: raise TypeError("Conv QVariant (update medico) falló")
            elif isinstance(medico_data_qvariant, dict): medico_data = medico_data_qvariant
            else: raise TypeError(f"Tipo inesperado: {type(medico_data_qvariant)}")
            if not isinstance(medico_data, dict): raise TypeError("Conversión update medico no resultó en dict")
        except Exception as e:
            print(f"Error conversión datos update medico: {e}"); traceback.print_exc()
            self.medicoUpdateResult.emit(False, "Error interno procesando datos para actualizar."); return

        # Procesar y guardar la foto (si se envió nueva en base64) y obtener la ruta
        try:
            # Pasar los datos actuales (que pueden incluir la ruta antigua) a la función helper
            ruta_foto_guardada = self._process_and_save_photo(medico_data) # Modifica medico_data quitando foto_base64
            medico_data['ruta_foto_perfil'] = ruta_foto_guardada # Añadir/Actualizar la ruta en los datos a guardar
        except Exception as e_proc:
            print(f"Error procesando foto durante UPDATE: {e_proc}")
            self.medicoUpdateResult.emit(False, f"Error procesando foto: {e_proc}"); return
            
        # Llamar a la lógica de negocio para actualizar el usuario
        try:
            success, message = self.medico_manager.update_details(medico_id, medico_data, current_user_id)
            print(f"BackendBridge: Resultado update médico: {success}, {message}")
            self.medicoUpdateResult.emit(success, message)
        except AttributeError:
            print("ERROR BackendBridge: Falta el método 'update_details' en MedicoActions.")
            self.medicoUpdateResult.emit(False, "Error interno: Funcionalidad de actualización no implementada.")
        except Exception as e:
            print(f"ERROR BackendBridge: Excepción llamando a medico_manager.update_details: {e}")
            traceback.print_exc()
            self.medicoUpdateResult.emit(False, f"Error interno durante la actualización: {e}")

    @pyqtSlot(result=QVariant) # ASEGÚRATE QUE ESTO ESTÁ
    def get_selected_medico_id(self):
        print(f"BackendBridge: Devolviendo ID médico para edición: {self.selected_medico_id_to_edit}")
        print(f"--- GETTING selected_medico_id_to_edit: Value={self.selected_medico_id_to_edit} (Tipo: {type(self.selected_medico_id_to_edit)}) ---")
        return QVariant(self.selected_medico_id_to_edit)

    @pyqtSlot(int, int)
    def set_selected_patient_and_consulta(self, p_id, c_id): # Nombres de argumentos diferentes
        print(f"PYTHON: set_selected_patient_and_consulta LLAMADO con P={p_id}, C={c_id}")
        self.selected_patient_id = p_id
        self.selected_consulta_id_for_edit = c_id


    @pyqtSlot() # <<<< CAMBIO: Esto es un slot, no un método de MainWindow
    def perform_logout(self):
        print("BackendBridge: Solicitud de logout recibida.")
        logout_user_id = None
        logout_username = "(Desconocido)"

        if self.current_user_data:
            logout_user_id = self.current_user_data.get('id')
            logout_username = self.current_user_data.get('username', logout_username)
            print(f"BackendBridge: Cerrando sesión para usuario: {logout_username} (ID: {logout_user_id})")
        else:
            print("BackendBridge: Logout solicitado, pero no había usuario activo.")
            logout_user_id = 0 # Usar ID sistema si no había sesión

        # Registrar acción de Logout
        conn_log = None
        try:
            conn_log = database.connect_db()
            if conn_log:
                with conn_log: # Usar transacción automática
                    descripcion = f"Cierre de sesión para usuario: {logout_username}."
                    # Asegurar que logout_user_id no sea None antes de llamar a log_action si es NOT NULL
                    if logout_user_id is None: logout_user_id = 0 # Fallback a sistema si algo raro pasó

                    database.log_action(
                        db_conn=conn_log,
                        usuario_id=logout_user_id, # ID del usuario que cierra sesión (o 0)
                        tipo_accion="LOGOUT",
                        descripcion=descripcion,
                        detalles={'username': logout_username if logout_username != "(Desconocido)" else None}
                    )
                    print(f"BackendBridge: Acción de logout registrada.")
            else:
                 print("BackendBridge Error: No se pudo conectar a BD para registrar log de logout.")
        except Exception as e:
            print(f"BackendBridge: Error general al registrar log de logout: {e}")
            traceback.print_exc()
        finally:
            if conn_log: conn_log.close()

        # Limpiar estado de sesión en el backend
        self.current_user_data = None
        self.selected_patient_id = None
        self.selected_medico_id_to_edit = None
        print("BackendBridge: Estado de sesión limpiado.")

        # Emitir señal para que el frontend recargue la página de login
        self.logoutComplete.emit()

    @pyqtSlot(int) # El ID del médico a cambiar de estado
    def toggle_medico_status(self, medico_id: int):
        print(f"--- BackendBridge: Solicitud toggle_medico_status para ID: {medico_id} ---")
        if not self.current_user_data or 'id' not in self.current_user_data:
            # Emitir error si no hay usuario logueado realizando la acción
            self.medicoStatusToggleResult.emit(False, "Error: Sesión no válida o usuario no identificado.", medico_id, -1) # -1 como estado inválido
            return
        
        current_user_id_actor = self.current_user_data['id']

        if medico_id == current_user_id_actor:
            print(f"--- BackendBridge WARNING: Usuario {current_user_id_actor} intentó desactivarse a sí mismo.")
            self.medicoStatusToggleResult.emit(False, "Error: No puedes cambiar tu propio estado de activación.", medico_id, -1)
            return

        try:
            success, message, nuevo_estado_int = self.medico_manager.toggle_status(medico_id, current_user_id_actor)
            print(f"--- BackendBridge: Resultado toggle_status desde MedicoActions: {success}, '{message}', nuevo_estado: {nuevo_estado_int} ---")
            self.medicoStatusToggleResult.emit(success, message, medico_id, nuevo_estado_int)
        except AttributeError:
            print("--- BackendBridge ERROR: MedicoActions no tiene el método 'toggle_status'. ---")
            self.medicoStatusToggleResult.emit(False, "Error interno del servidor (función no encontrada).", medico_id, -1)
        except Exception as e:
            print(f"--- BackendBridge ERROR: Excepción en toggle_medico_status: {e} ---")
            traceback.print_exc()
            self.medicoStatusToggleResult.emit(False, f"Error inesperado al cambiar estado: {e}", medico_id, -1)

    @pyqtSlot(QVariant)
    def update_ingreso_data(self, ingreso_data_qvariant):
        """Actualiza los datos de un ingreso (Consulta y ExamenFisico asociado)."""
        print("BackendBridge: Recibida solicitud para actualizar datos de ingreso...")

        if not self.current_user_data or 'id' not in self.current_user_data:
            self.updateIngresoDataResult.emit(False, "Error: Sesión no válida o usuario no identificado.")
            return
        current_user_id = self.current_user_data['id']

        try:
            ingreso_data_dict = self._convert_qvariant_to_dict(ingreso_data_qvariant, "datos de ingreso a actualizar")
            print(f"BackendBridge: Datos de ingreso convertidos: {list(ingreso_data_dict.keys())}")
        except TypeError as te:
            print(f"BackendBridge ERROR (update_ingreso_data - TypeError): {te}")
            self.updateIngresoDataResult.emit(False, f"Error interno procesando datos de ingreso: {te}")
            return
        except Exception as e_conv:
             print(f"BackendBridge ERROR (update_ingreso_data - Conversión): {e_conv}")
             traceback.print_exc()
             self.updateIngresoDataResult.emit(False, f"Error inesperado al procesar datos de ingreso: {e_conv}")
             return

        # El patient_id y consulta_id deben venir en el diccionario del formulario
        # y deben coincidir con los que tenemos seleccionados para evitar inconsistencias.
        form_patient_id = ingreso_data_dict.get('patient_id')
        form_consulta_id = ingreso_data_dict.get('consulta_id')

        try:
            form_patient_id = int(form_patient_id) if form_patient_id else None
            form_consulta_id = int(form_consulta_id) if form_consulta_id else None
        except ValueError:
            self.updateIngresoDataResult.emit(False, "Error: IDs de paciente/consulta inválidos en el formulario.")
            return

        if form_patient_id != self.selected_patient_id or form_consulta_id != self.selected_consulta_id_for_edit:
            print(f"BackendBridge ADVERTENCIA: Discrepancia de IDs al actualizar ingreso. Form: P{form_patient_id}/C{form_consulta_id}, Seleccionado: P{self.selected_patient_id}/C{self.selected_consulta_id_for_edit}")
            # Podrías optar por usar los IDs del formulario o los seleccionados, o emitir error.
            # Por seguridad, si hay discrepancia, podría ser un error.
            # Sin embargo, la práctica común es que el formulario envíe los IDs que está editando.
            # Aquí asumimos que los del formulario son los correctos para la actualización,
            # pero el log es útil.
            # Para mayor robustez, se podría forzar el uso de self.selected_patient_id y self.selected_consulta_id_for_edit
            # si se confía más en el estado del backend.
            # ingreso_data_dict['patient_id'] = self.selected_patient_id
            # ingreso_data_dict['consulta_id'] = self.selected_consulta_id_for_edit
            pass # Por ahora, dejamos que los del formulario pasen a la lógica de negocio.


        try:
            success, message = self.patient_manager.update_ingreso_data(ingreso_data_dict, current_user_id)
            print(f"BackendBridge: Resultado update_ingreso_data desde PatientActions: {success}, '{message}'")
            self.updateIngresoDataResult.emit(success, message)
        except AttributeError as ae:
            print(f"BackendBridge ERROR: PatientActions no tiene 'update_ingreso_data'. {ae}")
            self.updateIngresoDataResult.emit(False, "Error interno del servidor (función de actualización no encontrada).")
        except Exception as e:
            print(f"BackendBridge ERROR: Excepción en update_ingreso_data llamando a PatientActions: {e}")
            traceback.print_exc()
            self.updateIngresoDataResult.emit(False, f"Error inesperado al guardar cambios de ingreso: {e}")

    @pyqtSlot(int, int) # paciente_id, consulta_id (esta es la consulta a la que se asocia la nueva evolución)
    def set_context_for_new_evolucion(self, patient_id, consulta_id):
        print(f"BackendBridge: Contexto para nueva evolución: Paciente ID {patient_id}, Consulta ID {consulta_id}")
        self.selected_patient_id = patient_id # Ya lo usas
        self.selected_consulta_id_for_evolucion = consulta_id # Nuevo para saber a qué consulta pertenece la nueva evo

    @pyqtSlot(QVariant) # Recibe el diccionario de datos del formulario
    def save_new_evolucion(self, evolucion_data_qvariant):
        print("BackendBridge: Recibida solicitud para guardar NUEVA EVOLUCION...")

        # 1. Verificar Usuario y Paciente Seleccionado
        if not self.current_user_data or 'id' not in self.current_user_data:
            # Enviar error de sesión al handler de guardado de agregar_evolucion
            self.evolucionSaveResult.emit(False, "Error: Sesión no válida o usuario no identificado.", 0) # 0 como ID de evolución inválido
            return
        current_user_id = self.current_user_data['id']

        if not self.selected_patient_id:
             self.evolucionSaveResult.emit(False, "Error: Paciente no seleccionado.", 0)
             return

        # 2. Obtener el ID de la Consulta más reciente para este paciente
        consulta_id_para_nueva_evolucion = None
        try:
            # Asegúrate de que self.patient_actions está inicializado (debería estarlo en __init__)
            if hasattr(self, 'patient_actions') and self.patient_actions:
                consulta_id_para_nueva_evolucion = self.patient_actions.get_latest_consulta_id_for_patient(self.selected_patient_id)
                print(f"BackendBridge: Última consulta ID obtenida para paciente {self.selected_patient_id}: {consulta_id_para_nueva_evolucion}")
            else:
                print("BackendBridge ERROR: self.patient_actions no está disponible.")
                self.evolucionSaveResult.emit(False, "Error interno del servidor (PActions).", 0)
                return

        except Exception as e_consulta:
            print(f"BackendBridge ERROR: Excepción al obtener última consulta ID: {e_consulta}")
            traceback.print_exc()
            self.evolucionSaveResult.emit(False, f"Error al determinar la consulta asociada: {e_consulta}", 0)
            return

        if not consulta_id_para_nueva_evolucion:
            # Este es el error que estabas viendo si get_latest_consulta_id_for_patient devuelve None
            print(f"BackendBridge ERROR: No se encontró una consulta activa/reciente para el paciente ID {self.selected_patient_id}.")
            self.evolucionSaveResult.emit(False, "Error: No se pudo encontrar una consulta válida para asociar la evolución. ¿El paciente tiene una consulta activa?", 0)
            return

        print(f"BackendBridge: Guardando evolución para Paciente ID: {self.selected_patient_id}, Consulta ID: {consulta_id_para_nueva_evolucion}, Usuario ID: {current_user_id}")

        # 3. Convertir datos del formulario
        try:
            evolucion_data_dict = self._convert_qvariant_to_dict(evolucion_data_qvariant, "datos de nueva evolución")
        except TypeError as te:
            self.evolucionSaveResult.emit(False, f"Error interno procesando datos: {te}", 0)
            return
        except Exception as e_conv:
            print(f"BackendBridge ERROR (save_new_evolucion - Conversión): {e_conv}")
            traceback.print_exc()
            self.evolucionSaveResult.emit(False, f"Error inesperado al procesar datos de evolución: {e_conv}", 0)
            return

        # 4. Llamar a la acción de guardado en PatientActions
        # La función add_new_evolucion en PatientActions ya recibe patient_id, consulta_id, current_user_id
        success, message, new_evolucion_id = self.patient_actions.add_new_evolucion(
            evolucion_data=evolucion_data_dict,
            patient_id=self.selected_patient_id, # Se pasa para logging y consistencia
            consulta_id=consulta_id_para_nueva_evolucion,
            current_user_id=current_user_id
        )

        # 5. Emitir resultado (esto va al handler en agregar_evolucion.js)
        # Asegúrate de que el nombre de la señal aquí coincida con el que espera agregar_evolucion.js
        # El handler en agregar_evolucion.js se llama handleEvolucionSaveResult_pacientes__evolucion__agregar_evolucion
        # y la señal Python debería ser evolucionSaveResult (como ya la tienes).
        print(f"BackendBridge: Resultado de add_new_evolucion: {success}, {message}, ID: {new_evolucion_id}")
        self.evolucionSaveResult.emit(success, message, new_evolucion_id or 0)


    @pyqtSlot(int) # evolucion_id
    def set_selected_evolucion(self, evolucion_id):
        print(f"BackendBridge: Evolución seleccionada para ver/editar ID: {evolucion_id}")
        self.selected_evolucion_id_for_view_edit = evolucion_id
        # También necesitamos el patient_id para el botón "Volver" en ver/editar evolución,
        # así que nos aseguramos que selected_patient_id esté seteado desde el panel de evoluciones.
        # El patient_id se pasa al JS de ver/editar evolución usualmente como parámetro de URL/estado.

    @pyqtSlot()
    def request_evolucion_details(self):
        print(f"BackendBridge: Solicitud detalles para Evolución ID: {self.selected_evolucion_id_for_view_edit}")
        if self.selected_evolucion_id_for_view_edit is None:
            self.evolucionDetailsResult.emit(json.dumps({'error': 'No se seleccionó evolución.'}))
            return
        
        details = self.patient_manager.get_evolucion_details(self.selected_evolucion_id_for_view_edit)
        self.evolucionDetailsResult.emit(json.dumps(details, default=str)) # default=str para fechas

    @pyqtSlot(QVariant) # evolucion_id se obtiene de self.selected_evolucion_id_for_view_edit
    def update_evolucion_data(self, evolucion_data_qvariant):
        print(f"BackendBridge: Recibida solicitud para ACTUALIZAR EVOLUCION ID: {self.selected_evolucion_id_for_view_edit}")
        if not self.current_user_data or 'id' not in self.current_user_data:
            self.evolucionUpdateResult.emit(False, "Error: Sesión no válida.")
            return
        current_user_id = self.current_user_data['id']

        if self.selected_evolucion_id_for_view_edit is None:
            self.evolucionUpdateResult.emit(False, "Error: No hay evolución seleccionada para actualizar.")
            return
            
        try:
            evolucion_data_dict = self._convert_qvariant_to_dict(evolucion_data_qvariant, "datos de evolución a actualizar")
        except TypeError as te:
            self.evolucionUpdateResult.emit(False, f"Error interno procesando datos: {te}"); return

        success, message = self.patient_manager.update_evolucion(
            self.selected_evolucion_id_for_view_edit,
            evolucion_data_dict,
            current_user_id
        )
        self.evolucionUpdateResult.emit(success, message)




# --- Ventana Principal de la Aplicación ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sistema de Gestión - Gastroenterología")
        self.current_user = None

        try:
            screen = QApplication.primaryScreen()
            if screen: self.setMinimumSize(screen.availableGeometry().size())
            else: self.setMinimumSize(1024, 768)
        except Exception as e:
             print(f"MainWindow Error al obtener geometría pantalla ({e}). Usando fallback.")
             self.setMinimumSize(1024, 768)

        self.web_view = QWebEngineView()
        # El zoom puede causar problemas de renderizado en algunos sistemas,
        # considerar comentarlo si persisten los problemas de QtWebEngine.
        # self.web_view.setZoomFactor(1.3)

        print("MainWindow: Configurando QWebEngineView...")
        settings = self.web_view.settings()
        # Habilitar depuración remota (opcional para producción, útil para desarrollo)
        # La variable de entorno es una forma, otra es con argumentos a Chromium si es necesario
        
        
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True) # Puede ser deshabilitado si causa problemas

        self.channel = QWebChannel(self.web_view.page())
        self.web_view.page().setWebChannel(self.channel)

        self.backend_bridge = BackendBridge(self)
        self.channel.registerObject("backend", self.backend_bridge)

        self.backend_bridge.login_success.connect(self._handle_login_success)
        self.backend_bridge.login_failed.connect(self._handle_login_failed)
        self.backend_bridge.logoutComplete.connect(self._handle_logout_complete)

        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)
        layout.addWidget(self.web_view)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(central_widget)

        # La función get_absolute_path ahora usa self.backend_bridge.get_absolute_path
        # o puedes replicar la lógica de get_base_path aquí si MainWindow la necesita independientemente.
        # Por ahora, usaré una lógica similar a la de BackendBridge para MainWindow.
        self.load_page(os.path.join("html_files", "login.html"))

    def _get_main_window_base_path(self): # Lógica similar a BackendBridge.get_base_path
        try:
            base_path = sys._MEIPASS
        except AttributeError:
            base_path = os.path.abspath(os.path.dirname(__file__))
        if not hasattr(sys, '_MEIPASS') and getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        return base_path

    def get_absolute_path(self, relative_path):
        # Usa la lógica de base_path específica para MainWindow si es necesario,
        # o la de backend_bridge si es consistente.
        return os.path.join(self._get_main_window_base_path(), relative_path)


    def load_page(self, html_file_rel_path):
        file_path = self.get_absolute_path(html_file_rel_path)
        print(f"MainWindow: Cargando página completa: {file_path}")
        if os.path.exists(file_path):
            self.web_view.setUrl(QUrl.fromLocalFile(file_path))
        else:
            print(f"MainWindow Error: No se encontró {file_path}")
            self.web_view.setHtml(f"<h1>Error 404</h1><p>Archivo no encontrado: {html_file_rel_path}</p>")

    @pyqtSlot(dict)
    def _handle_login_success(self, user_data):
        print(f"MainWindow: Manejando login exitoso para {user_data.get('username')}")
        self.current_user = user_data
        self.load_page(os.path.join("html_files", "main_shell.html"))

    @pyqtSlot(str)
    def _handle_login_failed(self, error_message):
        print(f"MainWindow: Manejando login fallido: {error_message}")
        # ... (lógica para mostrar error en login.html) ...
        current_url = self.web_view.url().toString()
        if "login.html" in current_url:
             escaped_error = json.dumps(error_message)
             js_code = f"showLoginError({escaped_error});"
             self.web_view.page().runJavaScript(js_code)
        else: print("MainWindow: Login fallido detectado, pero no en página de login.")

    @pyqtSlot()
    def _handle_logout_complete(self):
        """Slot llamado cuando el backend termina el logout."""
        print("MainWindow: Recibida señal logoutComplete. Cargando página de login...")
        self.current_user = None # Limpiar usuario en MainWindow también
        # Recargar la página de login
        self.load_page(os.path.join("html_files", "login.html"))


        
    @pyqtSlot()
    def request_ingreso_details(self):
        """Solicita los detalles de un ingreso específico para edición."""
        print(f"BackendBridge: Solicitud de detalles de ingreso para Paciente ID: {self.selected_patient_id}, Consulta ID: {self.selected_consulta_id_for_edit}") # DEBUG

        if not self.selected_patient_id or not self.selected_consulta_id_for_edit:
            error_msg = "No se ha seleccionado un paciente o una consulta para editar."
            print(f"BackendBridge Error (request_ingreso_details): {error_msg}") # DEBUG
            self.ingresoDetailsResult.emit(json.dumps({"error": error_msg}))
            return
        
        try:
            ingreso_data = self.patient_manager.get_ingreso_details(
                self.selected_patient_id, 
                self.selected_consulta_id_for_edit
            )
            
            if ingreso_data and not ingreso_data.get("error"):
                print(f"BackendBridge (request_ingreso_details): Detalles de ingreso obtenidos. Serializando y emitiendo...") # DEBUG
                self.ingresoDetailsResult.emit(json.dumps(ingreso_data, default=str))
            else:
                error_detail = ingreso_data.get("error", "No se pudieron obtener los datos de ingreso.")
                print(f"BackendBridge Error (request_ingreso_details): {error_detail}") # DEBUG
                self.ingresoDetailsResult.emit(json.dumps({"error": error_detail}))
        except Exception as e:
            print(f"BackendBridge Error (request_ingreso_details): Excepción obteniendo datos de ingreso: {e}") # DEBUG
            traceback.print_exc()
            self.ingresoDetailsResult.emit(json.dumps({"error": f"Error interno obteniendo datos de ingreso: {str(e)}"}))


# --- Punto de Entrada Principal ---
if __name__ == "__main__":
    
    # Si estás usando la Opción 1 (AA_UseSoftwareOpenGL), la configuración
    # se haría ANTES de la siguiente línea, como se muestra comentado arriba.
    # Ejemplo:
    # print("INFO: Intentando establecer AA_UseSoftwareOpenGL...")
    # QCoreApplication.setAttribute(QtCoreQt.ApplicationAttribute.AA_UseSoftwareOpenGL, True)
    # print("INFO: AA_UseSoftwareOpenGL establecido.")

    app = QApplication(sys.argv)
    print("-" * 40 + "\nIniciando Aplicación Gastro...\n" + "-" * 40)
    
    # La configuración de Chromium args mediante variable de entorno YA SE HIZO ARRIBA.
    # No necesitas hacer nada más aquí para esa opción.

    print("Inicializando base de datos...")
    database.initialize_database()
    print("Asegurando usuario de prueba...")
    auth.create_test_user()
    print("Creando ventana principal...")
    main_window = MainWindow()
    print("Mostrando ventana principal (maximizada)...")
    main_window.showMaximized()
    print("-" * 40 + "\nAplicación iniciada. Bucle de eventos corriendo...")
    print("Para depurar JS, abre Chrome/Edge y navega a http://localhost:9223\n" + "-" * 40)
    sys.exit(app.exec())