# Code signing policy

Estado: SIN FIRMA. El propietario confirma que envio la solicitud a SignPath el 3 de octubre de 2026. Respuesta y aprobacion pendientes. Publicar fuentes bajo MIT no elimina el bloqueo de Smart App Control.

Se solicita la via gratuita de SignPath Foundation. Requiere un repositorio publico mantenido, origen verificable del fork, builds desde fuentes, MFA, roles definidos y aprobacion externa. No hay certificado emitido ni un plazo prometido. Politica: https://signpath.org/terms.html ; solicitud: https://signpath.org/apply.html .

El propietario confirma MFA de GitHub. El workflow Windows JR installer (unsigned) ya compilo los ejecutables Windows, ensamblo JR y genero/probo el instalador en un runner limpio: https://github.com/elbrendoh/AUTOCATCHSUBS/actions/runs/37171613819 . Source checks sigue siendo una verificacion independiente de sintaxis y overlays.

Trabajo pendiente durante la evaluacion: configurar roles y MFA en SignPath si se acepta el proyecto; revisar dependencias y politica de privacidad/activacion con SignPath; incorporar su proceso de firma y aprobar cada release. Solo tras aceptacion se usara la atribucion oficial de firma gratuita. No se atribuye una firma a SignPath antes de recibirla.

Propietario del repositorio y mantenedor propuesto para los roles de autor, revisor y aprobador: [elbrendoh](https://github.com/elbrendoh). La configuracion de roles y MFA en SignPath se realizara si se acepta el proyecto.

Se encontraron sin firma en JR: AUTOCATCHSUBS.exe, AUTOCATCHSUBSBackend.exe y las extensiones _cffi_backend, backports.zstd._zstd y cryptography._rust. El instalador tambien debe firmarse. El acceso a firma de un proyecto no autoriza firmar binarios upstream ajenos; consultar a sus mantenedores o reconstruir/revisar lo permitido por SignPath. La firma del instalador por si sola no garantiza la carga de bibliotecas bloqueadas.

Los artefactos oficiales deben firmarse despues de compilar y antes de generar sus manifiestos/instaladores finales. Ninguna actualizacion debe modificar un archivo despues de firmarlo. No se agregan exclusiones de Defender ni se desactiva Smart App Control.
