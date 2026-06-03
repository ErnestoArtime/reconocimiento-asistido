@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

rem ============================================================================
rem  Reconocimiento Asistido - Menu interactivo de servicios
rem  Uso: doble click o ejecutar `menu.bat` desde cmd/powershell en la raiz.
rem ============================================================================

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
rem Prefiere .venv311 (Python 3.11 con whisperx + pyannote) si existe.
rem Sino fallback a .venv (Python 3.14 sin diarizacion).
set "VENV=%ROOT%\.venv\Scripts\python.exe"
set "HF=%ROOT%\.venv\Scripts\hf.exe"
if exist "%ROOT%\.venv311\Scripts\python.exe" (
    set "VENV=%ROOT%\.venv311\Scripts\python.exe"
    set "HF=%ROOT%\.venv311\Scripts\hf.exe"
)
set "FRONT=%ROOT%\frontend-demo"
set "BACKEND_PORT=8000"
set "FRONTEND_PORT=3010"
set "BACKEND_LOG=%ROOT%\uvicorn.run.log"

:MENU
cls
echo ============================================================
echo   Reconocimiento Asistido - Menu
echo ============================================================
echo   Root: %ROOT%
echo.
echo   --- Servicios ---
echo   1. Lanzar BACKEND  (uvicorn :%BACKEND_PORT%)
echo   2. Lanzar FRONTEND (Next.js :%FRONTEND_PORT%)
echo   3. Lanzar AMBOS (consolas separadas)
echo   4. Parar TODO (backend + frontend + descargas)
echo.
echo   --- Estado / logs ---
echo   5. Estado procesos y puertos
echo   6. Ver log backend en vivo (tail)
echo   7. Health check backend (curl /health)
echo.
echo   --- Modelos ---
echo   8. Verify stack audio (FFmpeg + faster_whisper)
echo   9. Descargar modelo Whisper (HF)
echo  10. Listar modelos Ollama
echo  11. Pull modelo Ollama
echo.
echo   --- Utilidades ---
echo  12. Bench audio (multi provider)
echo  13. Test smoke transcripcion fichero
echo  14. Abrir frontend en navegador
echo  15. Editar .env
echo.
echo   --- Calidad / MVP (Hito 0+) ---
echo  16. Run pytest discover (suite completa)
echo  17. Run golden test runner (tests/golden)
echo  18. Bench LLM contra golden (scripts/golden_eval.py)
echo  19. Snapshot baseline (.env + smoke + paquetes)
echo  20. Cambiar DEPLOYMENT_PROFILE (demo/prototype_local/production)
echo  21. Validar contrato v1 endpoint (curl POST)
echo.
echo   0. Salir
echo ============================================================
set /p "OPT=Opcion: "

if "%OPT%"=="1"  goto OPT_BACKEND
if "%OPT%"=="2"  goto OPT_FRONTEND
if "%OPT%"=="3"  goto OPT_BOTH
if "%OPT%"=="4"  goto OPT_STOP_ALL
if "%OPT%"=="5"  goto OPT_STATUS
if "%OPT%"=="6"  goto OPT_TAIL
if "%OPT%"=="7"  goto OPT_HEALTH
if "%OPT%"=="8"  goto OPT_VERIFY
if "%OPT%"=="9"  goto OPT_HF_PULL
if "%OPT%"=="10" goto OPT_OLLAMA_LIST
if "%OPT%"=="11" goto OPT_OLLAMA_PULL
if "%OPT%"=="12" goto OPT_BENCH
if "%OPT%"=="13" goto OPT_SMOKE
if "%OPT%"=="14" goto OPT_OPEN_FRONT
if "%OPT%"=="15" goto OPT_EDIT_ENV
if "%OPT%"=="16" goto OPT_TEST_SUITE
if "%OPT%"=="17" goto OPT_GOLDEN_RUNNER
if "%OPT%"=="18" goto OPT_GOLDEN_EVAL
if "%OPT%"=="19" goto OPT_BASELINE
if "%OPT%"=="20" goto OPT_PROFILE_SWITCH
if "%OPT%"=="21" goto OPT_TEST_V1
if "%OPT%"=="0"  goto END
goto MENU


:OPT_BACKEND
echo.
echo [Backend] Lanzando uvicorn en consola nueva...
if not exist "%VENV%" (
    echo [ERROR] No existe %VENV%
    pause
    goto MENU
)
start "RECO-BACKEND" cmd /k "cd /d %ROOT% && %VENV% -m uvicorn app.main:app --host 127.0.0.1 --port %BACKEND_PORT% --reload"
timeout /t 2 >nul
echo Backend lanzado. Ventana titulo: RECO-BACKEND
pause
goto MENU


:OPT_FRONTEND
echo.
echo [Frontend] Lanzando Next.js en consola nueva...
if not exist "%FRONT%\package.json" (
    echo [ERROR] No existe %FRONT%\package.json
    pause
    goto MENU
)
start "RECO-FRONTEND" cmd /k "cd /d %FRONT% && npm run dev"
timeout /t 2 >nul
echo Frontend lanzado. Ventana titulo: RECO-FRONTEND
pause
goto MENU


:OPT_BOTH
echo.
echo [Both] Lanzando backend + frontend...
start "RECO-BACKEND" cmd /k "cd /d %ROOT% && %VENV% -m uvicorn app.main:app --host 127.0.0.1 --port %BACKEND_PORT% --reload"
timeout /t 2 >nul
start "RECO-FRONTEND" cmd /k "cd /d %FRONT% && npm run dev"
timeout /t 2 >nul
echo Ambos lanzados en consolas separadas.
pause
goto MENU


:OPT_STOP_ALL
echo.
echo [Stop] Parando todos los procesos del proyecto...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Get-CimInstance Win32_Process -Filter 'Name=''python.exe''' | Where-Object { $_.CommandLine -match 'reconocimiento-asistido|uvicorn|faster-whisper|hf\.exe' } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force; Write-Host ('killed python ' + $_.ProcessId) } catch {} };" ^
    "Get-CimInstance Win32_Process -Filter 'Name=''node.exe''' | Where-Object { $_.CommandLine -like '*reconocimiento-asistido*' } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force; Write-Host ('killed node ' + $_.ProcessId) } catch {} };" ^
    "Start-Sleep -Seconds 1;" ^
    "$p8000 = Get-NetTCPConnection -LocalPort %BACKEND_PORT% -State Listen -ErrorAction SilentlyContinue;" ^
    "if ($p8000) { Write-Host ('puerto %BACKEND_PORT% AUN LISTEN pid ' + $p8000.OwningProcess) } else { Write-Host 'puerto %BACKEND_PORT% libre' };" ^
    "$p3010 = Get-NetTCPConnection -LocalPort %FRONTEND_PORT% -State Listen -ErrorAction SilentlyContinue;" ^
    "if ($p3010) { Write-Host ('puerto %FRONTEND_PORT% AUN LISTEN pid ' + $p3010.OwningProcess) } else { Write-Host 'puerto %FRONTEND_PORT% libre' }"
echo.
pause
goto MENU


:OPT_STATUS
echo.
echo === Estado procesos y puertos ===
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Write-Host '--- python ---' -ForegroundColor Cyan;" ^
    "Get-CimInstance Win32_Process -Filter 'Name=''python.exe''' | Where-Object { $_.CommandLine -match 'reconocimiento-asistido|uvicorn' } | Select-Object ProcessId,@{n='Cmd';e={$_.CommandLine.Substring(0,[Math]::Min(120,$_.CommandLine.Length))}} | Format-Table -AutoSize -Wrap;" ^
    "Write-Host '--- node ---' -ForegroundColor Cyan;" ^
    "Get-CimInstance Win32_Process -Filter 'Name=''node.exe''' | Where-Object { $_.CommandLine -like '*reconocimiento-asistido*' } | Select-Object ProcessId,@{n='Cmd';e={$_.CommandLine.Substring(0,[Math]::Min(120,$_.CommandLine.Length))}} | Format-Table -AutoSize -Wrap;" ^
    "Write-Host '--- puertos ---' -ForegroundColor Cyan;" ^
    "Get-NetTCPConnection -State Listen -LocalPort %BACKEND_PORT%,%FRONTEND_PORT%,11434 -ErrorAction SilentlyContinue | Select-Object LocalPort,OwningProcess | Format-Table -AutoSize;"
pause
goto MENU


:OPT_TAIL
echo.
echo Tail backend log: %BACKEND_LOG%
echo (Ctrl+C para salir del tail)
if not exist "%BACKEND_LOG%" (
    echo [INFO] No existe log todavia. El backend escribe al log solo si se redirige.
    echo Mejor mira la ventana RECO-BACKEND directamente.
    pause
    goto MENU
)
powershell -NoProfile -Command "Get-Content -Path '%BACKEND_LOG%' -Wait -Tail 40"
goto MENU


:OPT_HEALTH
echo.
echo Health check: http://127.0.0.1:%BACKEND_PORT%/health
curl.exe -s -m 5 http://127.0.0.1:%BACKEND_PORT%/health
echo.
echo.
echo Providers audio:
curl.exe -s -m 5 http://127.0.0.1:%BACKEND_PORT%/api/audio/providers
echo.
pause
goto MENU


:OPT_VERIFY
echo.
echo Verify stack audio...
"%VENV%" "%ROOT%\scripts\verify_audio.py" --skip-model
echo.
pause
goto MENU


:OPT_HF_PULL
echo.
echo Modelos disponibles:
echo   tiny     ^|  75 MB  ^| muy rapido, baja calidad
echo   base     ^| 150 MB
echo   small    ^| 500 MB
echo   medium   ^| 1.5 GB  ^| sweet spot
echo   large-v3 ^| 3.0 GB  ^| maxima calidad
echo.
set /p "MODEL=Modelo (tiny/base/small/medium/large-v3): "
if "%MODEL%"=="" goto MENU
echo Descargando Systran/faster-whisper-%MODEL%...
"%HF%" download Systran/faster-whisper-%MODEL%
echo.
pause
goto MENU


:OPT_OLLAMA_LIST
echo.
echo Modelos Ollama:
ollama list
echo.
pause
goto MENU


:OPT_OLLAMA_PULL
echo.
echo Recomendados:
echo   qwen2.5:7b-instruct       (4.4 GB, sweet spot)
echo   qwen2.5:14b-instruct      (9 GB)
echo   llama3.1:8b               (4.9 GB)
echo   gemma3n:e4b               (3-4 GB)
echo   mistral-nemo:12b          (7 GB)
echo.
set /p "MODEL=Modelo a pull (en blanco = cancelar): "
if "%MODEL%"=="" goto MENU
ollama pull %MODEL%
echo.
pause
goto MENU


:OPT_BENCH
echo.
echo Bench audio sobre tests\audio_samples\ (necesita pares .wav + .txt)
set /p "PROVIDERS=Providers (separados por coma, blanco = todos): "
if "%PROVIDERS%"=="" (
    "%VENV%" "%ROOT%\scripts\audio_benchmark.py"
) else (
    "%VENV%" "%ROOT%\scripts\audio_benchmark.py" --providers %PROVIDERS%
)
echo.
pause
goto MENU


:OPT_SMOKE
echo.
set /p "AUDIO=Ruta del audio (arrastra fichero): "
set "AUDIO=%AUDIO:"=%"
if "%AUDIO%"=="" goto MENU
if not exist "%AUDIO%" (
    echo [ERROR] No existe: %AUDIO%
    pause
    goto MENU
)
echo Transcribiendo %AUDIO% ...
"%VENV%" -X utf8 -c "import sys, time; from app.services.audio.transcription_service import transcribe_upload; from app.core.config import get_settings; s=get_settings(); raw=open(r'%AUDIO%','rb').read(); t=time.perf_counter(); r=transcribe_upload(raw, r'%AUDIO%', s, use_cache=False); print(f'elapsed: {time.perf_counter()-t:.2f}s'); print(f'dur: {r.duration_s:.2f}s RTF: {r.rtf:.2f} provider: {r.provider} model: {r.model}'); print('---'); print(r.text)"
echo.
pause
goto MENU


:OPT_OPEN_FRONT
echo.
echo Abriendo http://localhost:%FRONTEND_PORT% ...
start "" "http://localhost:%FRONTEND_PORT%"
goto MENU


:OPT_EDIT_ENV
echo.
if exist "%ROOT%\.env" (
    notepad "%ROOT%\.env"
) else (
    echo [INFO] No existe .env. Creando desde .env.example...
    if exist "%ROOT%\.env.example" (
        copy "%ROOT%\.env.example" "%ROOT%\.env" >nul
        notepad "%ROOT%\.env"
    ) else (
        echo [ERROR] Tampoco existe .env.example
        pause
    )
)
goto MENU


:OPT_TEST_SUITE
echo.
echo === Suite completa pytest discover ===
"%VENV%" -m unittest discover -s tests -p "test_*.py" -v
echo.
pause
goto MENU


:OPT_GOLDEN_RUNNER
echo.
echo === Validacion shape + grafo del golden set ===
"%VENV%" -m unittest tests.golden.test_runner -v
echo.
pause
goto MENU


:OPT_GOLDEN_EVAL
echo.
echo Modelos para bench (separados por coma).
echo Sugeridos: heuristic, gemma4:e4b, qwen2.5:7b-instruct, llama3.1:8b
echo.
set /p "MODELS=Modelos (Enter=heuristic): "
if "%MODELS%"=="" set "MODELS=heuristic"
echo Bench contra tests/golden/...
"%VENV%" "%ROOT%\scripts\golden_eval.py" --models "%MODELS%"
echo.
echo Reporte: docs\baselines\<fecha>_bench.md
pause
goto MENU


:OPT_BASELINE
echo.
echo === Generando baseline (config + smoke test + paquetes) ===
"%VENV%" "%ROOT%\scripts\baseline_snapshot.py"
echo.
echo Output: docs\baselines\<fecha>.md
pause
goto MENU


:OPT_PROFILE_SWITCH
echo.
echo === Cambiar DEPLOYMENT_PROFILE ===
echo Perfiles validos: demo ^| prototype_local ^| production
echo Valor actual:
findstr /B "DEPLOYMENT_PROFILE=" "%ROOT%\.env" 2>nul
echo.
set /p "NEW_PROFILE=Nuevo perfil (Enter=cancelar): "
if "%NEW_PROFILE%"=="" goto MENU
if not "%NEW_PROFILE%"=="demo" if not "%NEW_PROFILE%"=="prototype_local" if not "%NEW_PROFILE%"=="production" (
    echo [ERROR] Perfil invalido: %NEW_PROFILE%
    pause
    goto MENU
)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$path = '%ROOT%\.env';" ^
    "if (-not (Test-Path $path)) { Copy-Item '%ROOT%\.env.example' $path }" ^
    ";" ^
    "$content = Get-Content $path -Raw;" ^
    "if ($content -match 'DEPLOYMENT_PROFILE=') {" ^
    "  $new = $content -replace 'DEPLOYMENT_PROFILE=.*', 'DEPLOYMENT_PROFILE=%NEW_PROFILE%';" ^
    "} else {" ^
    "  $new = 'DEPLOYMENT_PROFILE=%NEW_PROFILE%' + [System.Environment]::NewLine + $content;" ^
    "}" ^
    ";" ^
    "Set-Content -Path $path -Value $new -NoNewline -Encoding utf8"
echo Cambiado a %NEW_PROFILE%. Reinicia backend (opcion 4 + 1) para aplicar.
pause
goto MENU


:OPT_TEST_V1
echo.
echo === Test endpoint v1 (curl) ===
echo Modulo y seccion default: history / HABITOS
echo.
set /p "MODULE=Modulo (Enter=history): "
if "%MODULE%"=="" set "MODULE=history"
set /p "SECTION=Seccion (Enter=HABITOS): "
if "%SECTION%"=="" set "SECTION=HABITOS"
set /p "TEXT=Texto (Enter=demo): "
if "%TEXT%"=="" set "TEXT=El paciente no fuma actualmente y nunca ha fumado."
echo.
echo POST /api/v1/ia/extract-from-text
curl.exe -s -X POST http://127.0.0.1:%BACKEND_PORT%/api/v1/ia/extract-from-text ^
    -H "Content-Type: application/json" ^
    -d "{\"module\":\"%MODULE%\",\"section\":\"%SECTION%\",\"text\":\"%TEXT%\"}"
echo.
pause
goto MENU


:END
echo.
echo Saliendo. Los servicios lanzados (RECO-BACKEND, RECO-FRONTEND) siguen activos.
echo Usa opcion 4 para pararlos antes de cerrar.
echo.
endlocal
exit /b 0
