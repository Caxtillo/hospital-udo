# main.spec (Ajustado para la estructura de HOSPITAL)
# -*- mode: python ; coding: utf-8 -*-

import os
import sys # Necesario para sys._MEIPASS

# --- Función resource_path (Opcional pero seguro incluirla si la usas) ---
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        # Usar la ruta del directorio que contiene el script .py principal
        base_path = os.path.abspath(os.path.dirname(sys.argv[0])) 
        # O si prefieres relativo al .spec:
        # base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)
# ----------------------------------------------------

block_cipher = None

# --- Definir los archivos y carpetas de datos ---
app_data = [
    ('html_files', 'html_files'),             # Carpeta completa html_files -> html_files/
    ('123.sqlite', '.'),                      # BD 1 -> raíz del paquete
    ('gastro_db_encrypted.sqlite', '.'),      # BD 2 -> raíz del paquete
    ('secret.key', '.')                       # Clave secreta -> raíz del paquete
    # ('ruta/a/tu/icono.ico', '.')            # Icono si tienes
]
# -------------------------------------------------

a = Analysis(
    ['main.py'], # Script de entrada
    pathex=[], 
    binaries=[],
    datas=app_data, # Tus archivos y carpetas de datos
    hiddenimports=[ # Módulos que PyInstaller podría no ver
        'PySide2.QtXml',
        'PySide2.QtNetwork',  
        'PySide2.QtPrintSupport', 
        'sqlite3', # A veces necesita ser explícito
        # Añade 'openpyxl', 'qrcode', 'reportlab' SI los usas y dan error ModuleNotFound
        # Añade CUALQUIER otro módulo que dé error al ejecutar el .exe
        ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[], 
    win_no_prefer_redirects=False,
    win_private_assemblies=False, 
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts, 
    a.binaries, 
    a.zipfiles, 
    a.datas, 
    [],
    name='HospitalApp', # Cambia el nombre si quieres
    debug=False, 
    bootloader_ignore_signals=False,
    strip=False, 
    upx=True,    
    upx_exclude=[],
    runtime_tmpdir=None, 
    console=True,  # <-- EMPEZAR CON True para depurar
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None, 
    codesign_identity=None,
    entitlements_options=None,
    # icon='html_files/assets/tu_icono.ico' # <-- AJUSTA la ruta a tu icono si tienes
)