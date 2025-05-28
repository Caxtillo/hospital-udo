# main.py
import sys
import os
import traceback
import sqlite3
import json
import base64
import uuid
import platform
import subprocess
from datetime import datetime
import socket # Para obtener IP local
import threading # Para el servidor HTTP en segundo plano
import http.server
import socketserver
from urllib.parse import urlparse, parse_qs
import shutil


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

mobile_upload_sessions = {} 
UPLOAD_DIR_MOBILE_TEMP = "uploads_mobile_temp"

class MobileUploadHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        # ... (do_GET como lo tenías, no necesita cgi) ...
        parsed_path = urlparse(self.path)
        query_params = parse_qs(parsed_path.query)
        token = query_params.get('token', [None])[0]

        if not token or token not in mobile_upload_sessions:
            self.send_response(403)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h1>Acceso Denegado: Token Invalido o Expirado</h1>")
            return
        
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        html_content = f"""
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Subir Archivo</title>
            <style>
                body {{ font-family: sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 90vh; margin: 0; background-color: #f4f4f4; }}
                .container {{ background-color: white; padding: 25px; border-radius: 8px; box-shadow: 0 0 15px rgba(0,0,0,0.1); text-align: center; max-width: 400px; width: 90%; }}
                h1 {{ color: #333; margin-bottom: 20px; font-size: 1.5em; }}
                input[type="file"] {{ display: block; margin: 20px auto; padding: 10px; border: 1px solid #ddd; border-radius: 4px; width: calc(100% - 22px); }}
                button {{ background-color: #0d9488; color: white; padding: 12px 20px; border: none; border-radius: 4px; cursor: pointer; font-size: 1em; transition: background-color 0.3s; }}
                button:hover {{ background-color: #0a7066; }}
                .message {{ margin-top: 20px; font-size: 0.9em; }}
                .success {{ color: green; }}
                .error {{ color: red; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Subir Estudio Complementario</h1>
                <form id="uploadForm" method="post" action="/upload_file?token={token}" enctype="multipart/form-data">
                    <input type="file" name="file_to_upload" id="file_to_upload" required>
                    <button type="submit">Subir Archivo</button>
                </form>
                <div id="messageArea" class="message"></div>
            </div>
            <script>
                document.getElementById('uploadForm').addEventListener('submit', function(e) {{
                    e.preventDefault();
                    const formData = new FormData(this); // formData ahora incluye el archivo
                    const messageArea = document.getElementById('messageArea');
                    const fileInput = document.getElementById('file_to_upload');
                    
                    if (!fileInput.files || fileInput.files.length === 0) {{
                        messageArea.textContent = 'Por favor, seleccione un archivo.';
                        messageArea.className = 'message error';
                        return;
                    }}
                    
                    messageArea.textContent = 'Subiendo archivo...';
                    messageArea.className = 'message';

                    // No es necesario enviar el nombre del archivo por separado si el servidor puede parsear Content-Disposition
                    // Si el parseo del servidor es limitado, se podría añadir aquí:
                    // formData.append('original_filename', fileInput.files[0].name);

                    fetch(this.action, {{
                        method: 'POST',
                        body: formData // formData ya contiene el archivo y su nombre (en Content-Disposition)
                    }})
                    .then(response => response.json())
                    .then(data => {{
                        if (data.success) {{
                            messageArea.textContent = data.message || '¡Archivo subido con éxito!';
                            messageArea.className = 'message success';
                            document.getElementById('uploadForm').innerHTML = '<p class="success">Archivo enviado: ' + (data.filename_received || 'Archivo') + '. Puede cerrar esta ventana.</p>';
                        }} else {{
                            messageArea.textContent = 'Error: ' + (data.message || 'No se pudo subir el archivo.');
                            messageArea.className = 'message error';
                        }}
                    }})
                    .catch(error => {{
                        messageArea.textContent = 'Error de red o servidor: ' + error;
                        messageArea.className = 'message error';
                        console.error('Error en subida:', error);
                    }});
                }});
            </script>
        </body>
        </html>
        """
        self.wfile.write(html_content.encode('utf-8'))


    def parse_multipart_form_data(self):
        """
        Parsea 'multipart/form-data'. Devuelve un diccionario con campos
        y un diccionario con archivos {'fieldname': {'filename': '...', 'content': b'...'}}.
        Esto es una simplificación y puede no ser robusto para todos los casos.
        """
        ctype = self.headers.get('Content-Type')
        if not ctype or not ctype.startswith('multipart/form-data'):
            return {}, {}

        boundary = None
        parts = ctype.split(';')
        for part in parts:
            part = part.strip()
            if part.startswith('boundary='):
                boundary = part.split('=')[1].strip().encode() # Boundary debe ser bytes
                break
        
        if not boundary:
            return {}, {}

        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            return {}, {}

        body = self.rfile.read(content_length)
        
        form_data = {}
        file_data = {}
        
        # Separar por el boundary
        # El boundary en el cuerpo está precedido por '--'
        # El último boundary tiene '--' al final también
        split_boundary = b'--' + boundary
        items = body.split(split_boundary)
        
        # El primer y último item pueden ser vacíos o '--\r\n' después del split
        for item_bytes in items:
            if not item_bytes.strip() or item_bytes.strip() == b'--':
                continue

            # Cada item tiene headers y luego el contenido, separados por \r\n\r\n
            try:
                header_part_bytes, content_bytes = item_bytes.split(b'\r\n\r\n', 1)
            except ValueError: # No se pudo separar header y contenido
                continue
            
            # Decodificar headers (asumiendo utf-8 o ascii para headers)
            header_part_str = header_part_bytes.decode('latin-1', errors='ignore').strip() # latin-1 es común para headers http
            
            content_disposition = None
            name_attr = None
            filename_attr = None

            for header_line in header_part_str.split('\r\n'):
                if header_line.lower().startswith('content-disposition:'):
                    content_disposition = header_line.split(':', 1)[1].strip()
                    # Parsear atributos de Content-Disposition
                    # Ejemplo: form-data; name="file_to_upload"; filename="example.txt"
                    disp_parts = content_disposition.split(';')
                    for disp_part in disp_parts:
                        disp_part = disp_part.strip()
                        if disp_part.startswith('name='):
                            name_attr = disp_part.split('=', 1)[1].strip('"')
                        elif disp_part.startswith('filename='):
                            filename_attr = disp_part.split('=', 1)[1].strip('"')
            
            if name_attr:
                # Quitar el \r\n final del contenido si está presente
                if content_bytes.endswith(b'\r\n'):
                    content_bytes = content_bytes[:-2]

                if filename_attr: # Es un archivo
                    file_data[name_attr] = {'filename': filename_attr, 'content': content_bytes}
                else: # Es un campo de formulario normal
                    form_data[name_attr] = content_bytes.decode('utf-8', errors='replace') # Decodificar como texto

        return form_data, file_data


    def do_POST(self):
        parsed_path = urlparse(self.path)
        if parsed_path.path != '/upload_file':
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Endpoint no encontrado")
            return

        query_params = parse_qs(parsed_path.query)
        token = query_params.get('token', [None])[0]
        
        response_data = {}

        if not token or token not in mobile_upload_sessions:
            self.send_response(403, "Forbidden")
            self.send_header("Content-type", "application/json")
            self.end_headers()
            response_data = {'success': False, 'message': 'Token inválido o sesión expirada.'}
            self.wfile.write(json.dumps(response_data).encode('utf-8'))
            return

        form_fields, file_fields = self.parse_multipart_form_data()
            
        if 'file_to_upload' not in file_fields or not file_fields['file_to_upload'].get('content'):
            self.send_response(400, "Bad Request")
            self.send_header("Content-type", "application/json")
            self.end_headers()
            response_data = {'success': False, 'message': 'No se envió ningún archivo o el archivo está vacío.'}
            self.wfile.write(json.dumps(response_data).encode('utf-8'))
            return

        uploaded_file_info = file_fields['file_to_upload']
        file_content_bytes = uploaded_file_info['content']
        original_filename_from_mobile = uploaded_file_info.get('filename', f"mobile_upload_{uuid.uuid4().hex}.dat")

        try:
            # Crear directorio temporal si no existe
            # Obtener base_path de una forma accesible desde aquí. Si MobileUploadHandler no es anidada
            # y no tiene acceso directo a `self.get_base_path()` de BackendBridge,
            # necesitamos una forma de obtenerla.
            # Una opción es que BackendBridge pase el base_path al crear el handler o el servidor,
            # pero http.server no lo facilita. Otra es que `get_base_path` sea una función global
            # o un método estático de BackendBridge.
            # Por ahora, asumimos que BackendBridge está en el mismo módulo y podemos acceder a su método
            # a través de una instancia temporal (no ideal) o hacer get_base_path una función independiente.
            # Para este ejemplo, llamaré a una función get_application_base_path() que definirás globalmente o en BackendBridge.
            
            # Solución más simple: el directorio UPLOAD_DIR_MOBILE_TEMP se define relativo al script actual
            # (donde está main.py)
            current_script_dir = os.path.dirname(os.path.abspath(__file__))
            temp_upload_path_base = os.path.join(current_script_dir, UPLOAD_DIR_MOBILE_TEMP)
            os.makedirs(temp_upload_path_base, exist_ok=True)
            
            # Sanear el nombre de archivo original antes de usarlo en el path
            sane_original_filename = "".join(c for c in original_filename_from_mobile if c.isalnum() or c in ['.', '_', '-']).rstrip()
            if not sane_original_filename: # Si el nombre se vuelve vacío después de sanear
                sane_original_filename = f"upload_{uuid.uuid4().hex}.dat"


            # Generar un nombre de archivo único en el servidor usando el token y el nombre saneado
            server_filename_base, server_filename_ext = os.path.splitext(sane_original_filename)
            server_filename = f"{token}_{server_filename_base.replace('.', '_')}{server_filename_ext}" # Evitar múltiples puntos
            filepath_on_server = os.path.join(temp_upload_path_base, server_filename)

            with open(filepath_on_server, 'wb') as f:
                f.write(file_content_bytes)
            
            print(f"MobileUploadServer: Archivo '{original_filename_from_mobile}' (guardado como '{server_filename}') subido por token {token} a {filepath_on_server}")
            
            session_data = mobile_upload_sessions[token]
            session_data['status'] = 'uploaded'
            session_data['file_path'] = filepath_on_server
            session_data['file_name'] = original_filename_from_mobile # Usar el nombre real del archivo

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            response_data = {'success': True, 'message': f'Archivo "{original_filename_from_mobile}" subido.', 'filename_received': original_filename_from_mobile}
            self.wfile.write(json.dumps(response_data).encode('utf-8'))

        except Exception as e:
            print(f"MobileUploadServer: Error guardando archivo para token {token}: {e}")
            traceback.print_exc()
            if token in mobile_upload_sessions: # Asegurar que el token aún exista
                mobile_upload_sessions[token]['status'] = 'error'
                mobile_upload_sessions[token]['error_message'] = str(e)
            self.send_response(500)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            response_data = {'success': False, 'message': f'Error en el servidor al guardar: {str(e)}'}
            self.wfile.write(json.dumps(response_data).encode('utf-8'))

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
    ordenUpdateResult = pyqtSignal(bool, str)
    complementoDetailsResult = pyqtSignal(str) # (paciente_id, json_string_data_complemento)
    complementoSaveResult = pyqtSignal(bool, str, int) # (success, message, new_id or updated_id)
    mobileUploadUrlReady = pyqtSignal(str) # Envía JSON string: {url, token} o {error}
    mobileUploadStatus = pyqtSignal(str)

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
        self.selected_orden_id_for_view_edit = None
        self.selected_complemento_id_for_view_edit = None
        self.selected_orden_id_for_view_edit = None
        self.active_mobile_server_port = None # Para evitar múltiples servidores en el mismo puerto

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
    @pyqtSlot(int)
    def set_selected_complemento(self, complemento_id: int):
        print(f"BackendBridge: Complemento seleccionado para ver/editar ID: {complemento_id}")
        self.selected_complemento_id_for_view_edit = complemento_id

    @pyqtSlot(str)
    def abrir_archivo_sistema(self, path_relativo_o_absoluto_archivo: str):
        print(f"BackendBridge: Solicitud para abrir archivo en sistema: '{path_relativo_o_absoluto_archivo}'")

        if not path_relativo_o_absoluto_archivo:
            print("WARN: abrir_archivo_sistema recibió un path vacío.")
            return

        try:
            path_a_abrir = None
            if os.path.isabs(path_relativo_o_absoluto_archivo):
                path_a_abrir = path_relativo_o_absoluto_archivo
                print(f"BackendBridge: Ruta recibida ya es absoluta: '{path_a_abrir}'")
            else:
                # Convertir ruta relativa (ej: 'uploads/complementarios/...') a absoluta
                path_a_abrir = self.get_absolute_path(path_relativo_o_absoluto_archivo)
                print(f"BackendBridge: Ruta relativa convertida a absoluta: '{path_a_abrir}'")


            if not os.path.exists(path_a_abrir) or not os.path.isfile(path_a_abrir):
                print(f"ERROR: Archivo no encontrado en el sistema: {path_a_abrir}")
                # Podrías emitir una señal de error al frontend si es necesario
                # self.parent_window.web_view.page().runJavaScript(f"showUserAlert('error', 'El archivo adjunto no se encontró en el servidor.');")
                return

            current_os = platform.system()
            if current_os == "Windows":
                os.startfile(path_a_abrir)
                print(f"BackendBridge: os.startfile('{path_a_abrir}') llamado en Windows.")
            elif current_os == "Darwin": # macOS
                subprocess.call(["open", path_a_abrir])
                print(f"BackendBridge: subprocess.call(['open', '{path_a_abrir}']) llamado en macOS.")
            else: # Linux y otros Unix-like
                subprocess.call(["xdg-open", path_a_abrir])
                print(f"BackendBridge: subprocess.call(['xdg-open', '{path_a_abrir}']) llamado en Linux/Unix.")
            
        except Exception as e:
            print(f"ERROR al intentar abrir archivo '{path_a_abrir if 'path_a_abrir' in locals() else path_relativo_o_absoluto_archivo}' con aplicación del sistema: {e}")
            traceback.print_exc()
            # self.parent_window.web_view.page().runJavaScript(f"showUserAlert('error', 'No se pudo abrir el archivo adjunto con la aplicación del sistema.');")

    def get_local_ip_address(self):
        # Prioridad 1: Conexión a host externo para determinar la interfaz principal
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.1) 
            s.connect(('8.8.8.8', 1)) 
            ip = s.getsockname()[0]
            s.close()
            # Si devuelve 127.0.0.1, intentar el siguiente bloque para encontrar una IP de LAN
            if ip != '127.0.0.1':
                print(f"INFO: IP detectada (método socket connect): {ip}")
                return ip
        except Exception:
            pass # Continuar con otros métodos si este falla

        # Prioridad 2: Iterar sobre IPs de gethostbyname_ex y buscar IPs de LAN comunes
        try:
            hostname = socket.gethostname()
            all_ips_info = socket.gethostbyname_ex(hostname)
            # all_ips_info es una tupla: (hostname, aliaslist, ipaddrlist)
            # Iteramos sobre ipaddrlist
            for item_ip in all_ips_info[2]:
                if item_ip.startswith('192.168.') or \
                   item_ip.startswith('10.') or \
                   (item_ip.startswith('172.') and 16 <= int(item_ip.split('.')[1]) <= 31):
                    print(f"INFO: IP de LAN detectada (método gethostbyname_ex): {item_ip}")
                    return item_ip
        except Exception:
            pass

        # Prioridad 3: Usar comandos del sistema operativo (puede ser más lento)
        # Esta parte puede ser extensa y variar, la omito por brevedad pero la tienes de la respuesta anterior
        # Si usas esta parte, asegúrate que el parseo sea correcto y priorice IPs de LAN.
        # Ejemplo simplificado (solo para ilustrar el concepto):
        system_ips = []
        if platform.system() == "Windows":
            try:
                output = subprocess.check_output("ipconfig", universal_newlines=True, timeout=2)
                for line in output.split('\n'):
                    if 'IPv4 Address' in line or 'Dirección IPv4' in line :
                        parts = line.split(':')
                        if len(parts) > 1:
                            ip_candidate = parts[1].strip()
                            if ip_candidate and not ip_candidate.startswith('169.254') and not ip_candidate == '127.0.0.1':
                                system_ips.append(ip_candidate)
            except Exception: pass
        elif platform.system() == "Linux" or platform.system() == "Darwin":
            try: # hostname -I es bastante bueno en Linux
                output = subprocess.check_output(["hostname", "-I"], universal_newlines=True, timeout=2)
                candidates = output.strip().split()
                for candidate in candidates:
                    if not candidate == '127.0.0.1':
                        system_ips.append(candidate)
            except Exception: pass
        
        for sys_ip in system_ips:
             if sys_ip.startswith('192.168.') or \
                sys_ip.startswith('10.') or \
                (sys_ip.startswith('172.') and 16 <= int(sys_ip.split('.')[1]) <= 31):
                print(f"INFO: IP de LAN detectada (método OS command): {sys_ip}")
                return sys_ip


        # Último recurso si todo lo demás falla
        try:
            # Esto a menudo devuelve 127.0.0.1
            final_fallback_ip = socket.gethostbyname(socket.gethostname())
            print(f"WARN: Todos los métodos fallaron o no encontraron IP de LAN. Usando fallback final: {final_fallback_ip}")
            return final_fallback_ip
        except Exception:
            print(f"CRITICAL WARN: Falló incluso el último fallback para IP. Usando 127.0.0.1.")
            return "127.0.0.1"

    def find_available_port(self, start_port=8080, max_tries=100):
        for i in range(max_tries):
            port = start_port + i
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(("0.0.0.0", port)) # Intentar bindear
                return port
            except OSError: # Puerto en uso
                continue
        return None # No se encontró puerto disponible

    @pyqtSlot()
    def start_mobile_upload_session(self):
        print("BackendBridge: Solicitud para iniciar sesión de subida móvil.")
        try:
            # Detener cualquier servidor anterior si aún está activo (por si acaso)
            # Esta lógica necesitaría mejor gestión de hilos/servidores si hubiera múltiples sesiones concurrentes.
            # Por ahora, asumimos una sesión QR activa a la vez por instancia de la app.
            for token, session in list(mobile_upload_sessions.items()): # Iterar sobre copia para modificar
                if session.get('http_server'):
                    print(f"Cerrando servidor HTTP anterior para token {token} en puerto {session.get('port')}")
                    session['http_server'].shutdown()
                    session['http_server'].server_close()
                    if session.get('server_thread') and session['server_thread'].is_alive():
                        session['server_thread'].join(timeout=1)
                    del mobile_upload_sessions[token]


            ip_address = self.get_local_ip_address()
            if ip_address == "127.0.0.1" and platform.system() != "Linux": # En Linux 127.0.0.1 puede ser accesible en LAN a veces
                print("WARN: No se pudo obtener una IP local válida, usando 127.0.0.1. Puede no funcionar desde el móvil.")
                # Considerar emitir error al frontend o dar opción al usuario de ingresar IP
            
            port = self.find_available_port(start_port=8081) # Empezar desde 8081
            if port is None:
                self.mobileUploadUrlReady.emit(json.dumps({'error': 'No hay puertos disponibles para el servidor móvil.'}))
                return

            token = uuid.uuid4().hex
            # La URL que el móvil visitará para la página de subida
            # El endpoint del handler GET servirá la página.
            upload_page_url = f"http://{ip_address}:{port}/?token={token}" 

            # Directorio temporal global
            temp_dir = os.path.join(self.get_base_path(), UPLOAD_DIR_MOBILE_TEMP)
            os.makedirs(temp_dir, exist_ok=True)
            
            Handler = MobileUploadHandler
            # No podemos pasar `token` directamente a MobileUploadHandler de forma estándar.
            # El token se valida desde la URL en do_GET y do_POST.
            httpd = socketserver.TCPServer(("", port), Handler)
            
            print(f"MobileUploadServer: Iniciando servidor HTTP para subida móvil en {ip_address}:{port} con token {token}")
            print(f"MobileUploadServer: URL para QR: {upload_page_url}")

            # Guardar información de la sesión
            session_info = {
                'status': 'pending_qr_scan', 
                'file_path': None, 
                'file_name': None,
                'server_thread': None, 
                'http_server': httpd,
                'ip': ip_address,
                'port': port
            }
            mobile_upload_sessions[token] = session_info

            # Iniciar el servidor en un hilo separado para no bloquear la app Qt
            server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            session_info['server_thread'] = server_thread
            server_thread.start()
            
            self.active_mobile_server_port = port
            self.mobileUploadUrlReady.emit(json.dumps({'url': upload_page_url, 'token': token}))

        except Exception as e:
            print(f"Error en start_mobile_upload_session: {e}")
            traceback.print_exc()
            self.mobileUploadUrlReady.emit(json.dumps({'error': str(e)}))

    @pyqtSlot(str)
    def check_mobile_upload_status(self, token):
        # print(f"BackendBridge: Verificando estado para token {token}")
        if token in mobile_upload_sessions:
            session = mobile_upload_sessions[token]
            if session['status'] == 'uploaded':
                self.mobileUploadStatus.emit(json.dumps({
                    'token': token,
                    'uploaded': True,
                    'filePath': session['file_path'], # Enviar la ruta del servidor
                    'fileName': session['file_name']  # Enviar el nombre original (si se tiene)
                }))
                # Considerar limpiar la sesión aquí o después de que el formulario principal se guarde
                # self.cleanup_mobile_session(token) # Ejemplo
            elif session['status'] == 'error':
                 self.mobileUploadStatus.emit(json.dumps({
                    'token': token,
                    'uploaded': False,
                    'error': session.get('error_message', 'Error desconocido durante la subida.')
                }))
                 self.cleanup_mobile_session(token) # Limpiar en error
            else: # pending, qr_scanned_page_loaded, etc.
                self.mobileUploadStatus.emit(json.dumps({'token': token, 'uploaded': False, 'message': 'Esperando subida...'}))
        else:
            self.mobileUploadStatus.emit(json.dumps({'token': token, 'uploaded': False, 'error': 'Token no encontrado o sesión expirada.'}))

    def cleanup_mobile_session(self, token):
        if token in mobile_upload_sessions:
            session = mobile_upload_sessions.pop(token) # Eliminar de sesiones activas
            if session.get('http_server'):
                print(f"BackendBridge: Limpiando sesión y cerrando servidor para token {token} en puerto {session.get('port')}")
                try:
                    session['http_server'].shutdown() # Señal al servidor para que se detenga
                    session['http_server'].server_close() # Cierra el socket
                except Exception as e_shutdown:
                    print(f"Error al intentar shutdown/close del servidor HTTP para token {token}: {e_shutdown}")

            if session.get('server_thread') and session['server_thread'].is_alive():
                session['server_thread'].join(timeout=1) # Esperar a que el hilo termine

            # Eliminar archivo temporal si existe y si la política es borrarlo inmediatamente
            # file_to_delete = session.get('file_path')
            # if file_to_delete and os.path.exists(file_to_delete):
            #     try:
            #         os.remove(file_to_delete)
            #         print(f"Archivo temporal {file_to_delete} eliminado.")
            #     except Exception as e_del:
            #         print(f"Error eliminando archivo temporal {file_to_delete}: {e_del}")
            if self.active_mobile_server_port == session.get('port'):
                self.active_mobile_server_port = None
            print(f"Sesión para token {token} limpiada.")


    # Modificar save_new_complemento para manejar archivo de móvil
    @pyqtSlot(QVariant)
    def save_new_complemento(self, datos_complemento_qvariant):
        print("BackendBridge: Solicitud save_new_complemento")
        # ... (verificación de usuario como antes) ...
        if not self.current_user_data or 'id' not in self.current_user_data:
            self.complementoSaveResult.emit(False, "Error: Sesión no válida.", 0)
            return
        current_user_id = self.current_user_data['id']

        try:
            datos_comp = self._convert_qvariant_to_dict(datos_complemento_qvariant, "datos de nuevo complemento")
            
            paciente_id = datos_comp.get('paciente_id')
            # ... (validación de paciente_id como antes) ...

            archivo_path_guardado_enc = None # Path encriptado final para la BD
            
            # Priorizar archivo subido desde el móvil si existe la referencia
            if datos_comp.get('archivo_adjunto_movil_ref'):
                temp_server_path = datos_comp['archivo_adjunto_movil_ref']
                original_filename = datos_comp.get('archivo_adjunto_original_filename', 'archivo_movil.dat')
                
                print(f"Procesando archivo desde móvil: {temp_server_path}, nombre original: {original_filename}")

                if os.path.exists(temp_server_path) and os.path.isfile(temp_server_path):
                    # Mover/Copiar el archivo temporal a la ubicación final de 'uploads/complementarios'
                    # y luego encriptar esta nueva ruta relativa final.
                    
                    # Validar extensión (basado en el nombre original que debería venir del móvil)
                    allowed_extensions = [
                                            # Imágenes
                                            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', 
                                            # Documentos
                                            '.pdf', '.doc', '.docx', '.txt',
                                            # Videos
                                            '.mp4', '.mov', '.wmv', '.avi', '.mkv', '.webm', '.flv', '.mpeg', '.mpg' 
                                        ]
                    file_name_lower = original_filename.lower()
                    if not any(file_name_lower.endswith(ext) for ext in allowed_extensions):
                        # Si el tipo no es permitido, no lo procesamos. Informamos error.
                        # También deberíamos limpiar el archivo temporal.
                        self.complementoSaveResult.emit(False, "Error: Tipo de archivo móvil no permitido.", 0)
                        if os.path.exists(temp_server_path): os.remove(temp_server_path) # Limpiar
                        # También limpiar la sesión del token si aún existe
                        # (Necesitaríamos el token aquí o una forma de buscarlo por temp_server_path)
                        return

                    final_upload_dir = self.get_absolute_path(os.path.join('uploads', 'complementarios', str(paciente_id)))
                    os.makedirs(final_upload_dir, exist_ok=True)
                    
                    # Usar nombre original para el archivo final, pero hacerlo único
                    safe_filename_base = "".join(c for c in os.path.splitext(original_filename)[0] if c.isalnum() or c in [' ', '_', '-']).rstrip()
                    safe_filename_ext = os.path.splitext(original_filename)[1]
                    unique_final_filename = f"{uuid.uuid4().hex}_{safe_filename_base}{safe_filename_ext}"
                    
                    final_filepath_abs = os.path.join(final_upload_dir, unique_final_filename)
                    
                    try:
                        # Mover el archivo desde la ubicación temporal del servidor móvil
                        shutil.move(temp_server_path, final_filepath_abs) # O shutil.copy si quieres mantener el temporal por un tiempo
                        print(f"Archivo móvil movido de '{temp_server_path}' a '{final_filepath_abs}'")
                    except Exception as e_move:
                        print(f"Error moviendo archivo de móvil de temp a final: {e_move}. Intentando copiar...")
                        try:
                            shutil.copy(temp_server_path, final_filepath_abs)
                            os.remove(temp_server_path) # Eliminar el original si la copia fue exitosa
                            print(f"Archivo móvil copiado y original eliminado.")
                        except Exception as e_copy_del:
                            self.complementoSaveResult.emit(False, f"Error crítico al manejar archivo móvil: {e_copy_del}", 0)
                            return

                    final_archivo_path_relativo = os.path.join('uploads', 'complementarios', str(paciente_id), unique_final_filename).replace('\\', '/')
                    archivo_path_guardado_enc = self.db_manager.encrypt_data(final_archivo_path_relativo)

                    # Limpiar la sesión del token asociado a este temp_server_path
                    # Esto es un poco indirecto. Idealmente, el token viajaría con la data.
                    token_to_cleanup = None
                    for t, s_data in mobile_upload_sessions.items():
                        if s_data.get('file_path') == temp_server_path:
                            token_to_cleanup = t
                            break
                    if token_to_cleanup:
                        self.cleanup_mobile_session(token_to_cleanup)
                    else: # Si no se encontró, el archivo ya pudo haber sido limpiado o es un path antiguo
                        # Si el archivo temporal aún existe y no se encontró token, borrarlo igual.
                        if os.path.exists(temp_server_path): 
                            try: os.remove(temp_server_path)
                            except: pass 
                            
                else:
                    print(f"WARN: Referencia de archivo móvil '{temp_server_path}' no encontrada en el servidor. Se ignorará.")
                    # Podría emitirse un error o simplemente continuar sin adjunto.

            # Si no hay archivo móvil, o falló, intentar con el de PC (base64)
            elif datos_comp.get('archivo_adjunto_nuevo'):
                file_data = datos_comp['archivo_adjunto_nuevo'] # Este es el objeto con {name, base64, ...}
                # ... (lógica existente para procesar archivo_adjunto_nuevo - base64 de PC) ...
                try:
                    # ... (validación de extensión, decodificación, guardado) ...
                    # Esto es lo que ya tenías
                    allowed_extensions = [
                                            # Imágenes
                                            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', 
                                            # Documentos
                                            '.pdf', '.doc', '.docx', '.txt',
                                            # Videos
                                            '.mp4', '.mov', '.wmv', '.avi', '.mkv', '.webm', '.flv', '.mpeg', '.mpg' 
                                        ]
                    file_name_lower = file_data['name'].lower()
                    if not any(file_name_lower.endswith(ext) for ext in allowed_extensions):
                        self.complementoSaveResult.emit(False, "Error: Tipo de archivo (PC) no permitido.", 0)
                        return
                    decoded_content = base64.b64decode(file_data['base64'])
                    upload_dir = self.get_absolute_path(os.path.join('uploads', 'complementarios', str(paciente_id)))
                    os.makedirs(upload_dir, exist_ok=True)
                    
                    safe_filename_base = "".join(c for c in os.path.splitext(file_data['name'])[0] if c.isalnum() or c in [' ', '_', '-']).rstrip()
                    safe_filename_ext = os.path.splitext(file_data['name'])[1]
                    unique_filename = f"{uuid.uuid4().hex}_{safe_filename_base}{safe_filename_ext}"
                    
                    file_path_abs = os.path.join(upload_dir, unique_filename)
                    with open(file_path_abs, "wb") as f:
                        f.write(decoded_content)
                    
                    archivo_path_relativo = os.path.join('uploads', 'complementarios', str(paciente_id), unique_filename).replace('\\', '/')
                    archivo_path_guardado_enc = self.db_manager.encrypt_data(archivo_path_relativo)
                except Exception as e_file_pc:
                    self.complementoSaveResult.emit(False, f"Error al procesar archivo de PC: {e_file_pc}", 0); return


            # ... (resto de la lógica para insertar en BD con archivo_path_guardado_enc) ...
            conn = self.db_manager.connect_db()
            with conn:
                # ... (SQL INSERT y ejecución como antes, usando archivo_path_guardado_enc)
                # ...
                cursor = conn.cursor()
                sql = """INSERT INTO Complementarios (
                            paciente_id, consulta_id, orden_medica_id, 
                            usuario_registrador_id, fecha_registro, 
                            tipo_complementario, nombre_estudio, 
                            fecha_realizacion, resultado_informe, 
                            archivo_adjunto_path, estado, 
                            usuario_ultima_mod_id 
                         ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
                
                fecha_reg_str = datos_comp.get('fecha_registro')
                fecha_reg = datetime.fromisoformat(fecha_reg_str).isoformat() if fecha_reg_str else datetime.now().isoformat()
                fecha_realiz_str = datos_comp.get('fecha_realizacion')
                fecha_realiz = datetime.fromisoformat(fecha_realiz_str).isoformat() if fecha_realiz_str else None
                estado_comp_form = datos_comp.get('estado', 'Solicitado')

                valores_insert = (
                    paciente_id,
                    datos_comp.get('consulta_id') or None,
                    datos_comp.get('orden_medica_id') or None,
                    current_user_id,
                    fecha_reg,
                    datos_comp.get('tipo_complementario'),
                    self.db_manager.encrypt_data(datos_comp.get('nombre_estudio')),
                    fecha_realiz,
                    self.db_manager.encrypt_data(datos_comp.get('resultado_informe')) if datos_comp.get('resultado_informe') else None,
                    archivo_path_guardado_enc, # Este es el path encriptado del archivo final (móvil o PC)
                    estado_comp_form,
                    current_user_id
                )
                cursor.execute(sql, valores_insert)
                new_id = cursor.lastrowid
                self.db_manager.log_action(conn, current_user_id, 'CREAR_COMPLEMENTARIO', f"Complementario ID {new_id} creado.", 'Complementarios', new_id)

            self.complementoSaveResult.emit(True, "Estudio complementario guardado exitosamente.", new_id)

        except Exception as e:
            print(f"Error general en save_new_complemento: {e}"); traceback.print_exc()
            self.complementoSaveResult.emit(False, f"Error al guardar: {e}", 0)

    @pyqtSlot(int, QVariant)
    def update_complemento_data(self, complemento_id: int, datos_complemento_qvariant):
        print(f"BackendBridge: Solicitud update_complemento_data para ID: {complemento_id}")
        if not self.current_user_data or 'id' not in self.current_user_data:
            self.complementoSaveResult.emit(False, "Error: Sesión no válida.", complemento_id)
            return
        current_user_id = self.current_user_data['id']

        try:
            datos_comp = self._convert_qvariant_to_dict(datos_complemento_qvariant, "datos de complemento a actualizar")
            
            paciente_id_update = datos_comp.get('paciente_id')
            if not paciente_id_update: # paciente_id es NOT NULL en la tabla
                try:
                    paciente_id_update = int(paciente_id_update)
                except (ValueError, TypeError): # Si no se puede convertir, algo anda mal con los datos del form
                    self.complementoSaveResult.emit(False, "Error: ID de paciente inválido para actualizar.", complemento_id); return
            elif not paciente_id_update:
                 self.complementoSaveResult.emit(False, "Error: ID de paciente es requerido para actualizar.", complemento_id); return


            archivo_path_final_enc = None # Se determinará a continuación
            # Obtener path actual de la BD
            conn_check = self.db_manager.connect_db()
            cursor_check = conn_check.cursor()
            cursor_check.execute("SELECT archivo_adjunto_path FROM Complementarios WHERE id = ?", (complemento_id,))
            row_actual = cursor_check.fetchone()
            path_actual_enc_db = row_actual[0] if row_actual else None
            conn_check.close()

            if datos_comp.get('remove_current_attachment') and path_actual_enc_db:
                try:
                    path_actual_dec = self.db_manager.decrypt_data(path_actual_enc_db)
                    if path_actual_dec:
                        path_abs_borrar = self.get_absolute_path(path_actual_dec)
                        if os.path.exists(path_abs_borrar): os.remove(path_abs_borrar)
                except Exception as e_del: print(f"Error borrando adjunto (remove_current): {e_del}")
                archivo_path_final_enc = None # Se eliminó
            elif datos_comp.get('archivo_adjunto_nuevo'): # Hay nuevo archivo
                if path_actual_enc_db: # Borrar el viejo si existe, ya que se está subiendo uno nuevo
                    try:
                        path_actual_dec = self.db_manager.decrypt_data(path_actual_enc_db)
                        if path_actual_dec:
                            path_abs_borrar = self.get_absolute_path(path_actual_dec)
                            if os.path.exists(path_abs_borrar): os.remove(path_abs_borrar)
                    except Exception as e_del_old: print(f"Error borrando adjunto anterior (reemplazo): {e_del_old}")
                
                file_data = datos_comp['archivo_adjunto_nuevo']
                try:
                    allowed_extensions = [
                                            # Imágenes
                                            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', 
                                            # Documentos
                                            '.pdf', '.doc', '.docx', '.txt',
                                            # Videos
                                            '.mp4', '.mov', '.wmv', '.avi', '.mkv', '.webm', '.flv', '.mpeg', '.mpg' 
                                        ]
                    file_name_lower = file_data['name'].lower()
                    if not any(file_name_lower.endswith(ext) for ext in allowed_extensions):
                        self.complementoSaveResult.emit(False, "Error: Tipo de archivo no permitido. Solo imágenes o documentos.", 0 if is_new else complemento_id)
                        return
                    decoded_content = base64.b64decode(file_data['base64'])
                    upload_dir = self.get_absolute_path(os.path.join('uploads', 'complementarios', str(paciente_id_update)))
                    os.makedirs(upload_dir, exist_ok=True)
                    safe_filename_base = "".join(c for c in os.path.splitext(file_data['name'])[0] if c.isalnum() or c in [' ', '_', '-']).rstrip()
                    safe_filename_ext = os.path.splitext(file_data['name'])[1]
                    unique_filename = f"{uuid.uuid4().hex}_{safe_filename_base}{safe_filename_ext}"
                    file_path_abs = os.path.join(upload_dir, unique_filename)
                    with open(file_path_abs, "wb") as f: f.write(decoded_content)
                    archivo_path_relativo = os.path.join('uploads', 'complementarios', str(paciente_id_update), unique_filename).replace('\\', '/')
                    archivo_path_final_enc = self.db_manager.encrypt_data(archivo_path_relativo)
                except Exception as e_file:
                    self.complementoSaveResult.emit(False, f"Error al procesar nuevo archivo: {e_file}", complemento_id); return
            elif path_actual_enc_db: # No se borró y no hay nuevo, mantener el actual
                archivo_path_final_enc = path_actual_enc_db
            # Si no había, no se borró y no hay nuevo, archivo_path_final_enc sigue siendo None

            conn = self.db_manager.connect_db()
            with conn:
                cursor = conn.cursor()
                # fecha_ultima_mod se actualizará por DEFAULT CURRENT_TIMESTAMP
                # usuario_ultima_mod_id se actualizará al current_user_id
                sql = """UPDATE Complementarios SET
                            paciente_id = ?, consulta_id = ?, orden_medica_id = ?, 
                            tipo_complementario = ?, nombre_estudio = ?, 
                            fecha_realizacion = ?, fecha_registro = ?, 
                            resultado_informe = ?, archivo_adjunto_path = ?,
                            estado = ?, 
                            usuario_ultima_mod_id = ?,
                            fecha_ultima_mod = CURRENT_TIMESTAMP 
                         WHERE id = ?""" # 11 columnas a actualizar + id en WHERE
                
                fecha_reg_upd_str = datos_comp.get('fecha_registro')
                fecha_reg_upd = datetime.fromisoformat(fecha_reg_upd_str).isoformat() if fecha_reg_upd_str else datetime.now().isoformat()
                
                fecha_realiz_upd_str = datos_comp.get('fecha_realizacion')
                fecha_realiz_upd = datetime.fromisoformat(fecha_realiz_upd_str).isoformat() if fecha_realiz_upd_str else None

                valores_update = (
                    paciente_id_update,
                    datos_comp.get('consulta_id') or None,
                    datos_comp.get('orden_medica_id') or None,
                    datos_comp.get('tipo_complementario'),
                    self.db_manager.encrypt_data(datos_comp.get('nombre_estudio')),
                    fecha_realiz_upd,
                    fecha_reg_upd,
                    self.db_manager.encrypt_data(datos_comp.get('resultado_informe')) if datos_comp.get('resultado_informe') else None,
                    archivo_path_final_enc, # El path determinado arriba
                    datos_comp.get('estado'),
                    current_user_id, # usuario_ultima_mod_id
                    complemento_id
                )
                
                print(f"DEBUG: SQL para UPDATE Complemento: {sql}")
                print(f"DEBUG: Valores para UPDATE Complemento (longitud {len(valores_update)}): {valores_update}")
                
                cursor.execute(sql, valores_update)
                if cursor.rowcount == 0:
                     self.complementoSaveResult.emit(False, "Error: Estudio no encontrado o datos sin cambios.", complemento_id); return
                
                self.db_manager.log_action(conn, current_user_id, 'ACTUALIZAR_COMPLEMENTARIO', f"Complementario ID {complemento_id} actualizado.", 'Complementarios', complemento_id)
            
            self.complementoSaveResult.emit(True, "Estudio complementario actualizado exitosamente.", complemento_id)

        except sqlite3.ProgrammingError as prog_err:
            print(f"ERROR DE PROGRAMACIÓN SQL en update_complemento_data: {prog_err}"); traceback.print_exc()
            self.complementoSaveResult.emit(False, f"Error de BD (bindings): {prog_err}", complemento_id)
        except Exception as e:
            print(f"Error general en update_complemento_data: {e}"); traceback.print_exc()
            self.complementoSaveResult.emit(False, f"Error al actualizar: {e}", complemento_id)

    # request_complemento_details (como lo tenías, asegurando que las claves devueltas coincidan con lo que JS espera)
    @pyqtSlot()
    def request_complemento_details(self):
        # ... (tu código para request_complemento_details sin cambios significativos,
        # solo asegúrate que incluya 'estado' y que los campos desencriptados
        # tengan sufijos _dec si el JS los espera así) ...
        print(f"BackendBridge: Solicitud detalles para Complemento ID: {self.selected_complemento_id_for_view_edit}")
        if self.selected_complemento_id_for_view_edit is None:
            self.complementoDetailsResult.emit(json.dumps({'error_fetch': 'No se seleccionó ningún complemento para ver.'}))
            return

        conn = None
        try:
            conn = self.db_manager.connect_db()
            cursor = conn.cursor()
            sql_query = """
                SELECT 
                    comp.id AS id_complemento, comp.paciente_id AS paciente_id_real, comp.consulta_id, comp.orden_medica_id,
                    comp.tipo_complementario, comp.nombre_estudio, comp.fecha_realizacion, comp.fecha_registro,
                    comp.estado, comp.resultado_informe, comp.archivo_adjunto_path,
                    p.nombres AS paciente_nombres_enc, p.apellidos AS paciente_apellidos_enc, p.numero_historia AS numero_historia_paciente,
                    u_reg.nombre_completo AS usuario_registrador_nombre_enc, u_reg.nombre_usuario AS usuario_registrador_username
                FROM Complementarios comp
                JOIN Pacientes p ON comp.paciente_id = p.id
                JOIN Usuarios u_reg ON comp.usuario_registrador_id = u_reg.id
                WHERE comp.id = ?
            """
            cursor.execute(sql_query, (self.selected_complemento_id_for_view_edit,))
            row = cursor.fetchone()

            if not row:
                self.complementoDetailsResult.emit(json.dumps({'error_fetch': f'Complemento con ID {self.selected_complemento_id_for_view_edit} no encontrado.'}))
                return

            colnames = [desc[0] for desc in cursor.description]
            data_from_db = dict(zip(colnames, row))
            
            processed_data = {
                # ... (copiar otros campos como id_complemento, tipo_complementario, etc.)
                'id_complemento': data_from_db.get('id_complemento'),
                'paciente_id_real': data_from_db.get('paciente_id_real'),
                'consulta_id': data_from_db.get('consulta_id'),
                'orden_medica_id': data_from_db.get('orden_medica_id'),
                'tipo_complementario': data_from_db.get('tipo_complementario'),
                'fecha_realizacion': data_from_db.get('fecha_realizacion'),
                'fecha_registro': data_from_db.get('fecha_registro'),
                'numero_historia_paciente': data_from_db.get('numero_historia_paciente'),
                'estado' : data_from_db.get('estado')
            }

            # --- Desencriptación de Campos BLOB ---
            # Nombre Estudio
            nombre_estudio_blob = data_from_db.get('nombre_estudio')
            processed_data['nombre_estudio_dec'] = self.db_manager.decrypt_data(nombre_estudio_blob) if nombre_estudio_blob and isinstance(nombre_estudio_blob, bytes) else (str(nombre_estudio_blob) if nombre_estudio_blob else '')
            if "[Error" in processed_data['nombre_estudio_dec']: print(f"WARN: Error desencriptando nombre_estudio para complemento ID {processed_data['id_complemento']}")

            # Resultado Informe
            resultado_blob = data_from_db.get('resultado_informe')
            processed_data['resultado_informe_dec'] = self.db_manager.decrypt_data(resultado_blob) if resultado_blob and isinstance(resultado_blob, bytes) else (str(resultado_blob) if resultado_blob else '')
            if "[Error" in processed_data['resultado_informe_dec']: print(f"WARN: Error desencriptando resultado_informe para complemento ID {processed_data['id_complemento']}")

            # --- MANEJO DEL PATH DEL ARCHIVO ADJUNTO ---
            adjunto_path_blob = data_from_db.get('archivo_adjunto_path')
            path_para_webview_src = None # Este será el src final para la imagen
            ruta_relativa_desencriptada_original = None # Para el enlace de descarga
            if adjunto_path_blob and isinstance(adjunto_path_blob, bytes):
                try:
                    ruta_relativa_desencriptada_original = self.db_manager.decrypt_data(adjunto_path_blob)
                    if ruta_relativa_desencriptada_original:
                        path_absoluto_servidor = self.get_absolute_path(ruta_relativa_desencriptada_original)
                        
                        if os.path.exists(path_absoluto_servidor) and os.path.isfile(path_absoluto_servidor):
                            # Generar URL file:/// principalmente si es imagen, 
                            # aunque QWebEngine puede abrir PDFs con file:/// también.
                            # Para otros documentos (doc, docx), el navegador podría intentar descargarlos.
                            path_para_webview_src = QUrl.fromLocalFile(path_absoluto_servidor).toString()
                        else:
                            path_para_webview_src = "[Archivo No Encontrado en Servidor]"
                except Exception as e_decrypt_path:
                    path_para_webview_src = "[Error Procesando Path Adjunto]"
            
            processed_data['archivo_adjunto_path_para_src'] = path_para_webview_src 
            processed_data['archivo_adjunto_path_dec'] = ruta_relativa_desencriptada_original # La ruta original para el enlace


            # ... (desencriptar nombres de paciente y registrador como lo tenías)
            try:
                n_pac = self.db_manager.decrypt_data(data_from_db.get('paciente_nombres_enc')) if data_from_db.get('paciente_nombres_enc') else ''
                a_pac = self.db_manager.decrypt_data(data_from_db.get('paciente_apellidos_enc')) if data_from_db.get('paciente_apellidos_enc') else ''
                processed_data['paciente_nombre_completo_dec'] = f"{n_pac} {a_pac}".strip()
            except: processed_data['paciente_nombre_completo_dec'] = "[Error Nombre Paciente]"
            
            try:
                nombre_reg_enc = data_from_db.get('usuario_registrador_nombre_enc')
                processed_data['usuario_registrador_nombre_dec'] = self.db_manager.decrypt_data(nombre_reg_enc) if nombre_reg_enc else data_from_db.get('usuario_registrador_username', 'N/D')
            except: processed_data['usuario_registrador_nombre_dec'] = data_from_db.get('usuario_registrador_username', '[Err Usuario]')

            self.complementoDetailsResult.emit(json.dumps(processed_data, default=str))
        except Exception as e:
            print(f"Error en request_complemento_details: {e}"); traceback.print_exc()
            self.complementoDetailsResult.emit(json.dumps({'error_fetch': f'Error: {e}'}))
        finally:
            if conn: conn.close()

    @pyqtSlot(int, QVariant) # orden_id, datos_actualizados_qvariant
    def update_orden_data(self, orden_id: int, orden_data_qvariant):
        print(f"BackendBridge: Solicitud update_orden_data para Orden ID: {orden_id}")

        if not self.current_user_data or 'id' not in self.current_user_data:
            self.ordenUpdateResult.emit(False, "Error: Sesión no válida o usuario no identificado.")
            return
        current_user_id = self.current_user_data['id']

        if not orden_id or orden_id <= 0:
            self.ordenUpdateResult.emit(False, "Error: ID de orden inválido para actualizar.")
            return

        try:
            # Convertir QVariant a diccionario Python
            orden_actualizada_dict = self._convert_qvariant_to_dict(orden_data_qvariant, "datos de orden actualizados")
            print(f"BackendBridge: Datos de orden actualizados recibidos (primeras claves): {list(orden_actualizada_dict.keys())[:5]}")

            # Encriptar el objeto JSON completo
            # El diccionario ya debería tener el campo fecha_modificacion_orden actualizado por el JS
            json_string_to_encrypt = json.dumps(orden_actualizada_dict)
            encrypted_new_orden_json_blob = self.db_manager.encrypt_data(json_string_to_encrypt)

            # También actualizaremos la fecha_hora principal de la OrdenMedica para reflejar la edición
            fecha_modificacion_registro = datetime.now().isoformat()

            conn = self.db_manager.connect_db()
            with conn:
                cursor = conn.cursor()
                sql_update = """
                    UPDATE OrdenesMedicas
                    SET orden_json_blob = ?,
                        fecha_hora = ?, /* Actualizar la fecha principal de la orden */
                        usuario_id = ?  /* Quién está haciendo la modificación */
                    WHERE id = ?
                """
                # Nota: usuario_id aquí es quién realiza la MODIFICACIÓN.
                # Si quieres mantener el usuario_id original que CREÓ la orden,
                # no incluyas usuario_id en el SET. La práctica común es registrar
                # quién modificó, lo cual se puede hacer en el log o añadiendo
                # un campo usuario_ultima_mod_id a OrdenesMedicas si es necesario.
                # Por simplicidad y para coincidir con tu estructura de agregar,
                # actualizaremos el usuario_id al que edita.
                
                cursor.execute(sql_update, (
                    encrypted_new_orden_json_blob,
                    fecha_modificacion_registro,
                    current_user_id,
                    orden_id
                ))

                if cursor.rowcount == 0:
                    # Esto podría pasar si la orden fue borrada mientras se editaba,
                    # o si el orden_id es incorrecto.
                    self.ordenUpdateResult.emit(False, f"Error: No se encontró la orden ID {orden_id} para actualizar o no hubo cambios.")
                    print(f"BackendBridge: No se actualizó ninguna fila para Orden ID {orden_id}.")
                    return # Salir si no se actualizó nada

                # Registrar la acción
                # Necesitamos el patient_id para el log, lo obtenemos de la orden
                # (o lo pasas como argumento extra si es más fácil desde el JS)
                cursor.execute("SELECT c.paciente_id FROM OrdenesMedicas om JOIN Consultas c ON om.consulta_id = c.id WHERE om.id = ?", (orden_id,))
                paciente_id_row = cursor.fetchone()
                paciente_id_para_log = paciente_id_row[0] if paciente_id_row else "Desconocido"


                self.db_manager.log_action(
                    conn, current_user_id, 'ACTUALIZAR_ORDEN_MEDICA',
                    f"Orden médica ID {orden_id} actualizada para Paciente ID {paciente_id_para_log}.",
                    tabla='OrdenesMedicas', registro_id=orden_id,
                    detalles={'paciente_id': paciente_id_para_log, 'orden_id': orden_id}
                )
            
            self.ordenUpdateResult.emit(True, f'Orden médica ID {orden_id} actualizada exitosamente.')
            print(f"BackendBridge: Orden médica ID {orden_id} actualizada.")

        except TypeError as te:
            print(f"BackendBridge ERROR (update_orden_data - TypeError): {te}")
            traceback.print_exc()
            self.ordenUpdateResult.emit(False, f"Error interno procesando datos de orden para actualizar: {te}")
        except sqlite3.Error as db_err:
            print(f"DB Error en update_orden_data: {db_err}")
            traceback.print_exc()
            self.ordenUpdateResult.emit(False, f'Error de base de datos al actualizar la orden: {db_err}')
        except Exception as e:
            print(f"BackendBridge ERROR al actualizar orden médica: {e}")
            traceback.print_exc()
            self.ordenUpdateResult.emit(False, f'Error inesperado al actualizar la orden: {str(e)}')
        finally:
            if conn:
                conn.close()

    @pyqtSlot(QVariant, int) 
    def request_action_log_with_filters(self, filters_qvariant, page_number=1): # page_number con default
        filters = {}
        if isinstance(filters_qvariant, QVariant):
            filters_dict_candidate = filters_qvariant.toVariant()
            if isinstance(filters_dict_candidate, dict):
                filters = filters_dict_candidate
            else: # Si toVariant() no dio un dict, intentar con toJsonObject
                try:
                    filters = filters_qvariant.toJsonObject().toVariantMap()
                    if not isinstance(filters, dict): # Si aún no es dict, algo raro pasó
                        filters = {} 
                except AttributeError:
                    filters = {} # Fallback si no tiene los métodos JSON
        elif isinstance(filters_qvariant, dict): # Si ya se pasó como dict desde JS (menos probable con QVariant)
            filters = filters_qvariant
        
        # Asegurarse de que page_number sea un entero válido
        try:
            page = int(page_number)
            if page < 1: page = 1
        except (ValueError, TypeError):
            page = 1

        print(f"BackendBridge: Solicitud historial con filtros: {filters}, página: {page}")
        try:
            # Asegúrate que self.historial_manager.get_log espera 'page' y 'filters'
            logs, total_count = self.historial_manager.get_log(page=page, filters=filters)
            # La señal actionLogResult ya está definida para (list, int)
            self.actionLogResult.emit(logs or [], total_count or 0) 
        except Exception as e:
            print(f"BackendBridge Error: Excepción al obtener historial con filtros: {e}")
            traceback.print_exc()
            self.actionLogResult.emit([], 0)

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
    def request_view_content(self, view_name_with_separator_and_params): # Cambiado el nombre del parámetro
        print(f"BackendBridge: Solicitud recibida para vista: '{view_name_with_separator_and_params}'")

        # ***** SEPARAR EL NOMBRE BASE DE LA VISTA DE LOS PARÁMETROS *****
        view_name_base = view_name_with_separator_and_params
        if '?' in view_name_with_separator_and_params:
            view_name_base = view_name_with_separator_and_params.split('?', 1)[0]
        
        print(f"BackendBridge: Nombre base de la vista extraído: '{view_name_base}'")

        # Ahora usa view_name_base para el resto de la lógica
        path_parts_from_view_name = view_name_base.split('__')
        
        sane_path_components = []
        for part in path_parts_from_view_name:
            sane_component = "".join(c for c in part if c.isalnum() or c == '_')
            if not sane_component or sane_component != part:
                # Usar view_name_base aquí para el mensaje de error, ya que 'part' podría ser de una vista con params
                error_message = f"Componente de nombre de vista inválido ('{part}') en '{view_name_base}'."
                print(f"BackendBridge Error: {error_message}")
                error_html = f"<p style='color:red;'>Error: {error_message}</p>"
                # Emitir con el nombre original completo para que el JS sepa qué falló
                self.viewContentLoaded.emit(error_html, view_name_with_separator_and_params + "_error") 
                return
            sane_path_components.append(sane_component)

        if not sane_path_components:
            # Usar view_name_base para el mensaje
            error_message = f"Nombre de vista inválido o vacío después del procesamiento: '{view_name_base}'."
            print(f"BackendBridge Error: {error_message}")
            error_html = f"<p style='color:red;'>Error: {error_message}</p>"
            self.viewContentLoaded.emit(error_html, view_name_with_separator_and_params + "_error")
            return

        relative_fragment_path = os.path.join(*sane_path_components) + ".html"
        
        try:
            target_file_path = self.get_absolute_path(os.path.join("html_files", relative_fragment_path))
            # ... (resto de la lógica como antes, pero usando view_name_base para logs y errores si es relevante) ...
            
            print(f"BackendBridge: Intentando leer archivo fragmento: {target_file_path} (de vista base: {view_name_base})")

            base_html_dir_abs = os.path.abspath(self.get_absolute_path("html_files"))
            target_file_path_abs = os.path.abspath(target_file_path)

            if not target_file_path_abs.startswith(base_html_dir_abs + os.sep) and target_file_path_abs != base_html_dir_abs :
                print(f"BackendBridge Error: Path Traversal o fuera de 'html_files' para '{view_name_base}'. Path: '{target_file_path_abs}'")
                # ... emitir error ...
                self.viewContentLoaded.emit("<p style='color:red;'>Error de seguridad.</p>", view_name_with_separator_and_params + "_error_security")
                return

            if os.path.exists(target_file_path) and os.path.isfile(target_file_path):
                with open(target_file_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                print(f"BackendBridge: Contenido de '{relative_fragment_path}' leído. Enviando a JS...")
                # Emitir con el nombre original COMPLETO para que JS lo use para inicializar (JS leerá los params del hash)
                self.viewContentLoaded.emit(html_content, view_name_with_separator_and_params)
            else:
                error_message = f"Archivo fragmento NO encontrado para vista base '{view_name_base}': {target_file_path}"
                print(f"BackendBridge Error: {error_message}")
                # ... emitir error ...
                self.viewContentLoaded.emit(f"<p style='color:red;'>Vista '{view_name_base}' no encontrada.</p>", view_name_with_separator_and_params + "_error_not_found")
        except Exception as e:
            # ... emitir error ...
            self.viewContentLoaded.emit(f"<p style='color:red;'>Error interno cargando '{view_name_base}'.</p>", view_name_with_separator_and_params + "_error_internal")


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