# Compilacion Windows x64

Requisitos: Python 3.12, Node.js, Rust estable, Visual Studio C++ Build Tools (Windows SDK, LLVM y CMake), Vulkan SDK e Inno Setup. Clona en una ruta corta para evitar limites de CMake/Windows. No se requiere ninguna clave privada para compilar JR.

Para comprobar la sintaxis de Python/JavaScript y reproducir los overlays de UI sin activar licencias, ejecuta `python tools/verify-source.py`. El workflow Source checks ejecuta esta misma verificacion; no compila ni firma los ejecutables Windows.

1. Instala las dependencias Python de `requirements-build.txt` en un entorno virtual.
2. Coloca un FFmpeg Windows x64 obtenido de una distribucion verificable en `AUTOCATCHSUBS-release-source/binaries/ffmpeg-x86_64-pc-windows-msvc.exe`. Conserva sus licencias y procedencia. No se incluye un binario de terceros en el ZIP de fuentes.
3. En una terminal de desarrollador x64, configura `VULKAN_SDK` y `LIBCLANG_PATH`. Ejecuta `tools/build-native.ps1 -Edition jr` o `-Edition admin`.
4. Ejecuta `python AUTOCATCHSUBS-licensing/build_backend.py jr` (o admin) para el runtime empaquetado. Los fuentes ya preparados incluyen el guard nativo y Python.
5. Para trabajar sobre los cambios de UI, ejecuta `node ui/overrides/patch_ui.cjs`. Conserva los assets del baseline y copia sus salidas a `dist-admin`/`dist-jr`; JR usa puertos 56202/56203/56204. Las distribuciones incluidas ya contienen los cambios r9 y el overlay de activacion.
6. Para un instalador se deben ensamblar el cliente, runtime Python, recursos Lua y dependencias oficiales; generar `manifest.json` con SHA256 por archivo; validar las licencias de terceros; firmar los ejecutables y bibliotecas; compilar `installer.iss` y firmar el instalador. El archivo de Inno exige paquete completo y WebView2 oficial.

La compilacion nativa de la version instalada se valido en el entorno del mantenedor. Este paquete exportado no afirma una compilacion desde clon limpio ni una aprobacion de firma. El trabajo pendiente de integracion de CI y dependencias de terceros se describe en CODE_SIGNING.md.

## Servicio propio

El servicio y el cliente estan publicados como fuente, no como identidad compartida. Para crear un despliegue independiente, genera tu propia boveda con `admin.py`, crea D1, aplica `schema.sql`, configura los secretos del Worker y usa tu endpoint/clave publica al compilar. Usa `wrangler.example.jsonc`. No reutilices ni solicites la identidad privada del mantenedor.

No ejecutes `init`, `seed` o exportaciones contra la boveda del propietario como parte de una compilacion o CI. Compilar JR no genera ni consume licencias.
