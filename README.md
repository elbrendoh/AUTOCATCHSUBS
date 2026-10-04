# AUTOCATCHSUBS

Open source bajo licencia MIT. Fork para DaVinci Resolve de [Auto Subs v3.8.0](https://github.com/tmoroney/auto-subs/tree/v3.8.0), manteniendo sus avisos de autoria y licencias de dependencias.

AUTOCATCHSUBS automatiza subtitulos con Whisper local, seleccion de audio, vista previa editable y Text+. Incluye cache de estilos, filtro por identidad de generador, busqueda, favoritos, progreso, Console lateral, Deshacer breve y tutorial.

## Ediciones y activacion

AUTOCATCHSUBS es Admin; AUTOCATCHSUBS JR es la distribucion para editores.
JR oficial conserva activacion mediante un codigo permanentemente vinculado a una PC. No se libera ni rota; revocar no lo devuelve a Libre. Despues de activar se permite trabajo offline. Una revocacion llega al reconectar.

Este repositorio contiene las fuentes de ambos clientes y del servicio de licencias. No incluye codigos reales, la boveda, identidad de firma del servicio ni token Admin. La configuracion del cliente contiene exclusivamente endpoint y clave publica.

La licencia MIT permite modificar y compilar el software. Por ello, conservar el control de activacion en la distribucion oficial no impide que otras personas creen versiones modificadas; el servidor mantiene el vinculo permanente de los codigos originales.

## Fuentes y construccion

- `AUTOCATCHSUBS-release-source`: Rust/Tauri y assets actuales.
- `AUTOCATCHSUBS-backend-source`: Python legible Admin/JR, sin datos privados.
- `AUTOCATCHSUBS-packages/*/resources`: Lua y macros de Resolve.
- `upstream-ui`: fuentes React/TypeScript originales conservadas.
- `ui/overrides`: cambios propios legibles y generador de la interfaz actual.
- `AUTOCATCHSUBS-licensing/service`: Worker y esquema D1 publicables.

Consulta [BUILD.md](BUILD.md), [PRIVACY.md](PRIVACY.md) y [CODE_SIGNING.md](CODE_SIGNING.md).

## Estado de distribucion

El codigo esta publicado bajo MIT. El propietario confirma que envio la solicitud a SignPath el 3 de octubre de 2026; respuesta y aprobacion pendientes. Todavia no cuenta con firma reconocida de distribucion. Windows con Control inteligente de aplicaciones puede bloquear los ejecutables actuales. No se cambia ni desactiva la seguridad del equipo.

Las pruebas del lanzador directo y de los controles de licencia siguen pasando. El ZIP de fuentes no es un nuevo instalador firmado ni una confirmacion de apertura en la PC bloqueada.
