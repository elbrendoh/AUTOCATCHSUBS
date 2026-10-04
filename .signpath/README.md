# Preparacion para SignPath

Estado: integracion preparada, desactivada. La Foundation aun no ha aprobado el proyecto.
No hay firma emitida, certificado configurado ni garantia de aceptacion.

## Que ya hace el workflow

El build Windows genera un artefacto separado con solo `AUTOCATCHSUBS.exe` y
`AUTOCATCHSUBSBackend.exe`, compilados por GitHub desde este repositorio. Verifica
su nombre de producto y version, conserva hashes y no incluye claves ni estado.
El instalador habitual sigue marcado como **unsigned**.

El job opcional `sign-own-binaries` utiliza la accion oficial de SignPath fijada
al commit `f6d04783b4569d051e0c80105fe66e82819d0092` (v3). Solo se habilita
mediante un lanzamiento manual desde `main`, el parametro
`submit_own_binaries=true` y la variable `SIGNPATH_ENABLED=true`.
Recibe firmas, verifica confianza Windows, certificado aprobado, timestamp,
RSA, metadatos y que el contenido de los ejecutables no haya cambiado.
Publica un artefacto de **dos binarios propios**, nunca una release ni un
instalador final. No consume licencias de produccion.

## Configuracion cuando llegue la aprobacion

1. Seguir las instrucciones de la Foundation para el acceso, MFA y roles.
2. Instalar la [aplicacion GitHub de SignPath](https://github.com/apps/signpath)
   solo para `elbrendoh/AUTOCATCHSUBS`, y configurar GitHub.com como Trusted Build
   System en SignPath. Usar el repositorio real y restringir origen a `main`.
3. Crear una configuracion de artefacto con
   [jr-binaries.xml](artifact-configurations/jr-binaries.xml).
   Sus dos rutas son exactas: ninguna DLL, PYD ni FFmpeg se firma con nuestra identidad.
4. Crear/configurar la politica con aprobacion manual exigida por la Foundation.
5. En GitHub, Settings > Environments, preparar `signpath-release` con aprobador
   requerido y limitado a `main`, segun las instrucciones de SignPath. Si pide
   un revisor distinto del autor, agregarlo antes de habilitar solicitudes.
6. Guardar el token del submitter como **secret de ese environment**:
   `SIGNPATH_API_TOKEN`. Nunca ponerlo en un archivo, commit, log o mensaje.
7. Configurar estas variables del repositorio o del environment (son publicas):

| Variable | Valor que entrega/configura SignPath |
| --- | --- |
| `SIGNPATH_ORGANIZATION_ID` | ID de la organizacion aprobada |
| `SIGNPATH_PROJECT_SLUG` | Slug del proyecto |
| `SIGNPATH_SIGNING_POLICY_SLUG` | Slug de la politica con aprobacion manual |
| `SIGNPATH_ARTIFACT_CONFIGURATION_SLUG` | Slug de la configuracion JR exacta |
| `SIGNPATH_CERTIFICATE_THUMBPRINT` | Thumbprint SHA1 de 40 caracteres del certificado publico aprobado |

8. Solo despues de verificar todo, crear **en el repositorio**
   `SIGNPATH_ENABLED=true`. Antes de eso, no hay llamadas a SignPath.
9. Actions > Windows JR installer (unsigned) > Run workflow: `main`, seleccionar
   `submit_own_binaries`. Aprobar el environment y despues la solicitud en SignPath.
   La espera de firma tiene limite de 30 minutos. Si caduca, revisar la solicitud
   existente antes de repetir el build; no aprobar duplicados a ciegas.

No copiar un certificado autofirmado ni usar un certificado de pruebas para
afirmar que Windows confiara en una distribucion. Al renovar el certificado,
revisar y actualizar expresamente el thumbprint aprobado.

## Falta para el instalador final

Las firmas de nuestros dos ejecutables son una etapa, no la distribucion completa.

- Resolver con SignPath/upstream los cuatro archivos de terceros sin firma:
  FFmpeg de BtbN, `_cffi_backend`, `backports.zstd._zstd`, `cryptography._rust`.
  El proyecto no puede firmar esos binarios ajenos con su identidad.
- Integrar los binarios firmados **antes** de regenerar el manifiesto y empaquetar.
  El manifiesto unsigned actual no puede reutilizarse despues de firmar archivos.
- Firmar tambien el desinstalador Inno y las copias temporales del instalador.
  [Inno admite una compilacion inicial para generar el desinstalador y otra con
  su firma ya incorporada](https://jrsoftware.org/ishelp/topic_setup_signeduninstaller.htm).
  La firma de `Setup.exe` por si sola no cubre `unins000.exe`.
- Compilar y firmar el instalador final, verificar instalacion/desinstalacion y
  la apertura en la PC con Smart App Control. Esta comprobacion aun no se hizo.
- Revisar con la Foundation activacion, privacidad, opciones de red y condiciones
  del fork. Su elegibilidad sigue pendiente.

No sustituir instalaciones actuales ni publicar una release firmada hasta
completar esas etapas. Las bibliotecas de terceros conservan sus propios
avisos, origen y firmas; no se modifican ni se vuelven a firmar durante el staging.

## Referencias oficiales

- [Integracion GitHub](https://docs.signpath.io/trusted-build-systems/github)
- [Configuracion de artefactos](https://docs.signpath.io/artifact-configuration/syntax)
- [Restricciones de metadatos](https://docs.signpath.io/artifact-configuration/examples)
- [Condiciones OSS](https://signpath.org/terms.html)

La configuracion XML y el job estan preparados y sujetos a validacion en el
panel aprobado de SignPath; las pruebas locales no reemplazan esa validacion.
