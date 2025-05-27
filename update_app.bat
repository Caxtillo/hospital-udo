@echo off
echo ===========================================
echo      Actualizador de la Aplicacion       
echo ===========================================
echo.

echo Verificando estado de Git...
git status -s
REM El -s es para salida corta, si no hay cambios no muestra nada. 
REM Si hay cambios locales no commiteados, se mostrarán aquí.

echo.
echo Tirando de los ultimos cambios desde el servidor (origin main)...
git pull origin main

REM Comprobar si git pull tuvo éxito (esto es una comprobación básica)
IF ERRORLEVEL 1 (
    echo.
    echo !!! ERROR: Hubo un problema al ejecutar 'git pull'. !!!
    echo Por favor, revisa los mensajes de error de Git arriba.
    echo Puede que necesites resolver conflictos manualmente si modificaste archivos localmente.
    goto End
)

echo.
echo Cambios del servidor aplicados.
echo.

REM Comprobar si requirements.txt cambió y si existe un entorno virtual común
IF EXIST requirements.txt (
    git diff --quiet HEAD@{1} HEAD -- requirements.txt
    IF ERRORLEVEL 1 (
        echo ATENCION: El archivo 'requirements.txt' ha cambiado.
        echo Es posible que necesites actualizar las dependencias.
        echo.
        IF EXIST .\.venv\Scripts\activate.bat (
            echo Para actualizar (si usas un entorno .venv):
            echo   1. Activa tu entorno: .\.venv\Scripts\activate
            echo   2. Ejecuta: pip install -r requirements.txt
            echo   3. Desactiva: deactivate
        ) ELSE (
            echo Si usas un entorno virtual, actívalo y ejecuta:
            echo   pip install -r requirements.txt
        )
        echo.
    ) ELSE (
        echo 'requirements.txt' no tuvo cambios significativos respecto a la version anterior.
    )
)

:End
echo.
echo ===========================================
echo      Proceso de actualizacion finalizado.
echo ===========================================
echo.
pause