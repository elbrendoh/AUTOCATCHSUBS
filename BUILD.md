# Compilacion Windows x64

Requisitos: Python 3.12, Node.js, Rust estable, Visual Studio C++ Build Tools (Windows SDK, LLVM y CMake), Vulkan SDK e Inno Setup. Clona en una ruta corta para evitar limites de CMake/Windows. No se requiere ninguna clave privada para compilar JR.

Para comprobar la sintaxis de Python/JavaScript y reproducir los overlays de UI sin activar licencias, ejecuta `python tools/verify-source.py`. El workflow Source checks ejecuta esta misma verificacion; no compila ni firma los ejecutables Windows.

1. Instala las dependencias Python de `requirements-build.txt` en un entorno virtual.
2. Coloca un FFmpeg Windows x64 obtenido de una distribucion verificable en `AUTOCATCHSUBS-release-source/binaries/ffmpeg-x86_64-pc-windows-msvc.exe`. Conserva sus licencias y procedencia. No se incluye un binario de terceros en el ZIP de fuentes.
3. En una terminal de desarrollador x64, configura `VULKAN_SDK` y `LIBCLANG_PATH`. Ejecuta `tools/build-native.ps1 -Edition jr` o `-Edition admin`.
4. Ejecuta `python AUTOCATCHSUBS-licensing/build_backend.py jr` (o admin) para el runtime empaquetado. Los fuentes ya preparados incluyen el guard nativo y Python.
5. Para trabajar sobre los cambios de UI, ejecuta `node ui/overrides/patch_ui.cjs`. Conserva los assets del baseline y copia sus salidas a `dist-admin`/`dist-jr`; JR usa puertos 56202/56203/56204. Las distribuciones incluidas ya contienen los cambios r9 y el overlay de activacion.
6. Para un instalador se deben ensamblar el cliente, runtime Python, recursos Lua y dependencias oficiales; generar `manifest.json` con SHA256 por archivo; validar las licencias de terceros; firmar los ejecutables y bibliotecas; compilar `installer.iss` y firmar el instalador. El archivo de Inno exige paquete completo y WebView2 oficial.

La primera compilacion del instalador JR desde el repositorio publico paso en un runner limpio de GitHub: https://github.com/elbrendoh/AUTOCATCHSUBS/actions/runs/37171613819 . Esto no es una aprobacion de firma ni una prueba de timeline en Resolve. Las revisiones posteriores deben comprobarse en sus propios runs.

## GitHub Actions: instalador JR de prueba

El workflow `Windows JR installer (unsigned)` construye en `windows-2022` usando Rust 1.99.0, Python 3.12 y el Cargo.lock publicado. Se puede iniciar en Actions con Run workflow. Las acciones estan fijadas por commit; `tools/ci-dependencies.json` fija URL/SHA256 de Vulkan SDK, FFmpeg LGPL e Inno Setup. WebView2 es el bootstrapper Evergreen oficial: se verifica su firma Microsoft y se registra el hash de cada descarga.

El proceso reconstruye los overlays de interfaz, ejecuta las regresiones sinteticas Text+/licencias, compila Rust/Tauri, congela Python, ensambla JR, genera hashes y verifica el runtime sin activacion. Compila el instalador de Inno y prueba instalar/desinstalar en un perfil temporal del runner, incluyendo el registro y retirada del menu Lua. No se ejecuta el instalador en la PC del mantenedor.

La salida es un artifact temporal con `AUTOCATCHSUBSJR-Setup.exe` SIN FIRMA y `build-provenance.json`, asociado al commit. Un segundo artifact conserva informes de dependencias, firmas y pruebas durante 3 dias. No se publica automaticamente una release ni se usa ningun secreto de Cloudflare, boveda o codigo real.

Un build correcto no certifica Smart App Control ni una timeline real: esas verificaciones siguen pendientes para la distribucion firmada. Revisar cumplimiento de licencias/fuentes de terceros antes de una release definitiva. Despues de obtener firma deben regenerarse los hashes del paquete y reconstruirse/firmarse el instalador; no editar binarios firmados.

## Servicio propio

El servicio y el cliente estan publicados como fuente, no como identidad compartida. Para crear un despliegue independiente, genera tu propia boveda con `admin.py`, crea D1, aplica `schema.sql`, configura los secretos del Worker y usa tu endpoint/clave publica al compilar. Usa `wrangler.example.jsonc`. No reutilices ni solicites la identidad privada del mantenedor.

No ejecutes `init`, `seed` o exportaciones contra la boveda del propietario como parte de una compilacion o CI. Compilar JR no genera ni consume licencias.
