# Privacidad

La transcripcion de audio se procesa localmente. No se envian audio ni proyectos al servicio de licencias.

JR solicita activacion explicitamente al usuario. Al activar envia el codigo, la huella de hardware, el nombre del equipo y el perfil/nombre del editor al endpoint HTTPS configurado. El servicio guarda hashes de codigo y la vinculacion al dispositivo. La huella no es un numero de serie publico ni se incluye en el ZIP de fuentes.

Una vez activado, el cliente consulta su estado periodicamente cuando hay conexion. Trabajar offline conserva la autorizacion firmada; la primera activacion necesita Internet y una revocacion nueva no llega hasta reconectar. Las preferencias/licencias se conservan durante actualizaciones. El usuario puede desinstalar el programa por Windows.

Los modelos pueden descargarse de Hugging Face y las dependencias oficiales de sus proveedores. El proyecto utiliza Cloudflare Workers/D1 para licencias: https://www.cloudflare.com/privacypolicy/ y https://huggingface.co/privacy . No se habilita telemetria de proyectos.

Revision pendiente para SignPath: incorporar esta politica al instalador y revisar con la Foundation la activacion obligatoria de JR y las opciones de red requeridas. No se afirma que ese requisito este aprobado.
