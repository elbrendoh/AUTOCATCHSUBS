# Code signing policy

Estado: SIN FIRMA / SIN SOLICITUD APROBADA. Publicar fuentes bajo MIT no elimina el bloqueo de Smart App Control.

Se pretende solicitar la via gratuita de SignPath Foundation. Requiere un repositorio publico mantenido, origen verificable del fork, builds desde fuentes, MFA, roles definidos y aprobacion externa. No hay certificado emitido ni un plazo prometido. Politica: https://signpath.org/terms.html ; solicitud: https://signpath.org/apply.html .

Antes de enviar: definir el mantenedor/committer, revisores y aprobador de releases en GitHub; documentar el fork de Auto Subs; crear CI de construccion verificable; revisar dependencias y politica de privacidad/activacion con SignPath. Solo tras aceptacion se usara la atribucion oficial de firma gratuita. No se atribuye una firma a SignPath antes de recibirla.

Se encontraron sin firma en JR: AUTOCATCHSUBS.exe, AUTOCATCHSUBSBackend.exe y las extensiones _cffi_backend, backports.zstd._zstd y cryptography._rust. El instalador tambien debe firmarse. El acceso a firma de un proyecto no autoriza firmar binarios upstream ajenos; consultar a sus mantenedores o reconstruir/revisar lo permitido por SignPath. La firma del instalador por si sola no garantiza la carga de bibliotecas bloqueadas.

Los artefactos oficiales deben firmarse despues de compilar y antes de generar sus manifiestos/instaladores finales. Ninguna actualizacion debe modificar un archivo despues de firmarlo. No se agregan exclusiones de Defender ni se desactiva Smart App Control.
