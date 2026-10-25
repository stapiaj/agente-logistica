# Lecciones de método

> Archivo vivo. Aquí se apunta lo que funciona bien o mal **en la forma de trabajar** (no en el código). Al terminar el proyecto se destila en la "Guía de proyectos con IA" para el siguiente.
>
> Formato: `- AAAA-MM-DD · [etiqueta] Qué pasó → qué haríamos en el próximo proyecto.`
> Etiquetas: `[producto]` `[planificación]` `[chats-IA]` `[git]` `[entorno]` `[aprendizaje]` `[seguridad]`

## Funcionó bien

- 2026-10-19 · [chats-IA] Separar `docs/contexto/` (fijo) de `docs/estado/` (vivo) → el conocimiento del proyecto se sube una vez y el estado se lee siempre de la carpeta. Mantenerlo.
- 2026-10-19 · [chats-IA] Protocolo de inicio y cierre de chat con `progreso.md` + `bitacora.md` → cada chat retoma sin pérdidas aunque no recuerde nada. Mantenerlo desde el día 1.
- 2026-10-19 · [chats-IA] Chat principal que planifica y revisa + chats de proyecto con encargos de alcance cerrado → los chats devolvieron sus dudas al principal en lugar de decidir por su cuenta. Mantenerlo.
- 2026-10-19 · [aprendizaje] Cerrar cada fase rompiendo algo a propósito y con 3 preguntas de repaso → obliga a entender, no solo a que funcione.
- 2026-10-21 · [chats-IA] Probar el bucle y el guardarraíl con un "Gemini falso" con guion antes de gastar llamadas reales → detecta fallos de lógica sin cuota ni 503. Mantenerlo.
- 2026-10-21 · [aprendizaje] Ante un fallo del agente, cambiar una cosa y repetir el mismo caso con el mismo modelo → el arreglo se mide, no se supone. Mantenerlo.
- 2026-10-21 · [aprendizaje] Predecir antes de ejecutar cada rotura y comparar después → las sorpresas (el modelo que reescribe el id) enseñan más que los aciertos.
- 2026-10-22 · [chats-IA] El chat principal entregó el encargo con las decisiones ya tomadas y su porqué → el chat de ejecución no tuvo que reabrir debates y solo preguntó lo que de verdad faltaba (p. ej. formato inválido de `new_eta`). Mantenerlo.
- 2026-10-22 · [aprendizaje] Guardar una ejecución "antes" del arreglo (aunque fuera por accidente) y repetir la misma después → la mejora se ve en una tabla (2 avisos → 1). Hacerlo a propósito.
- 2026-10-22 · [planificación] Probar cada integración primero sin LLM (modo `smoke`: leer, escribir y releer) y solo después con el agente → la integración se valida sin gastar cuota y, si algo falla con el agente, ya se sabe que no es la conexión. Mantenerlo en la 3b (Resend, Telegram).
- 2026-10-22 · [aprendizaje] Comprobar releyendo del sistema real lo que el código dice que ha escrito (el log se relee de la hoja) → se confía en el destino, no en el mensaje de Python. Mantenerlo.
- 2026-10-22 · [chats-IA] Probar el adaptador y los fallos de la hoja con una hoja simulada antes de que Sergio ejecutara → apareció un mensaje engañoso del guardarraíl ("log escrito" sin estarlo) sin gastar llamadas. Mantenerlo.
- 2026-10-23 · [seguridad] Probar la red de seguridad con la configuración incompleta (sin `EMAIL_TEST_RECIPIENT`) reveló que fallaba abierta → en lo irreversible, probar a propósito qué pasa si falta la protección y hacer que falle cerrado.
- 2026-10-23 · [seguridad] Diagnosticar un secreto sin mostrarlo (longitud, partes, caracteres raros) → resolvió el 401 de Telegram sin exponer el token. Mantenerlo.
- 2026-10-23 · [aprendizaje] Repetir la misma rotura con el modelo mostró dos caminos distintos (se saltó el aviso / avisó y falló) → con LLM, repetir la rotura si el camino importa, y cubrir cada camino con un check determinista sin LLM.
- 2026-10-23 · [planificación] Un archivo de checks sin LLM que crece tarea a tarea (`fase3b_checks.py`) → cada tarea se valida en segundos y sin cuota antes de gastar llamadas reales. Mantenerlo desde la primera tarea de cada fase.
- 2026-10-23 · [aprendizaje] Cuando Sergio se perdió con el código del webhook, explicarlo primero en funcional (historia de un aviso, analogías de timbre y ventanilla, tabla "qué pasa si falla") y solo después señalar en qué archivo vive cada paso → lo entendió y lo pudo contar. Para conceptos nuevos de arquitectura: funcional antes que código.
- 2026-10-24 · [aprendizaje] Una rotura que "no rompía" (el 401 no salía) se investigó en vez de saltarla → apareció que VS Code carga el `.env` en cada terminal y `load_dotenv()` no lo pisa. Cuando una rotura no sale como se predijo, diagnosticar antes de seguir: suele esconder la mejor lección.
- 2026-10-23 · [chats-IA] Probar el diseño en el entorno de la IA con las mismas versiones antes de dárselo a Sergio (orden secreto/cuerpo en FastAPI, checks de la T8) → apareció el matiz del JSON mal formado antes de que confundiera. Mantenerlo.

- 2026-10-25 · [aprendizaje] Dejar fallar a propósito el primer despliegue (sin variables) → Sergio aprendió a leer los logs de Render con un error conocido antes de necesitarlo de verdad. Para cada plataforma nueva, provocar primero un fallo controlado.
- 2026-10-25 · [chats-IA] Comprobar en la documentación de la plataforma lo que cambia con el tiempo (Python por defecto en Render 3.14, ruta de los archivos secretos, servicios gratuitos) antes de proponer → evitó un cambio de versión silencioso. Mantenerlo para cualquier servicio externo.
- 2026-10-25 · [planificación] Desplegar la rama de la fase y cambiar a `main` al fusionar → se pudo probar en producción sin romper "un PR por fase". Mantenerlo.
- 2026-10-25 · [aprendizaje] Ante un resultado inesperado en producción (el email del pegado), pedir pruebas (logs, ejecuciones) antes de explicar → el diagnóstico salió de los datos y apareció un límite real del diseño.

## A mejorar

- 2026-10-19 · [chats-IA] El conocimiento del proyecto de Claude estaba vacío y ningún chat lo detectó (funcionaba solo porque leían la carpeta) → al configurar un proyecto, comprobar explícitamente que el conocimiento está cargado.
- 2026-10-19 · [git] El flujo de rama + PR por fase se decidió después de la fase 0 → decidir el flujo Git (y si el repo será público) antes de empezar.
- 2026-10-19 · [entorno] Git antiguo y credenciales de otra cuenta de GitHub hicieron perder tiempo en la fase 0 → incluir en la fase 0 una comprobación de versiones y de la cuenta de GitHub activa.
- 2026-10-21 · [producto] No se escribió una especificación (usuario, alcance, MVP, métricas de éxito, riesgos) antes de programar → en el próximo proyecto, `especificacion.md` acordada antes de la primera línea de código.
- 2026-10-21 · [producto] Las decisiones se registraron en una línea, sin alternativas ni consecuencias → usar `decisiones.md` con formato decisión / contexto / alternativas / por qué / consecuencias.
- 2026-10-21 · [producto] El stack lo propuso la IA y Sergio lo aceptó → en decisiones relevantes, la IA presenta opciones con pros y contras y decide Sergio.
- 2026-10-21 · [planificación] Las tareas vivían solo en documentos → probar issues, hitos y tablero de GitHub Projects para que la planificación sea visible.
- 2026-10-21 · [planificación] El idioma (código, commits, docs, README) se decidió sobre la marcha → fijarlo al inicio, pensando en quién va a leer el repo.
- 2026-10-21 · [entorno] Comandos de prueba en una sola línea (`python -c`) y bloques `@'` de PowerShell resultaron difíciles de leer y de pegar → para pruebas de más de 2 líneas, un script en `scripts/` desde el principio.
- 2026-10-21 · [planificación] La cuota gratuita de Gemini (20 peticiones/día por modelo) se agotó a mitad de fase: un agente gasta una llamada por vuelta → estimar llamadas por caso y configurar modelos de respaldo antes de lanzar baterías de pruebas.
- 2026-10-21 · [chats-IA] La IA usó `role="tool"` de ejemplos genéricos y la API de Gemini no lo acepta → contrastar el formato de la conversación con la documentación del proveedor concreto.
- 2026-10-22 · [chats-IA] Sergio lanzó una prueba antes de que el cambio estuviera implementado (el OK y la prueba se cruzaron) → al proponer un cambio, separar claramente "propuesta, espera OK" de "hecho, ahora prueba"; y en la propuesta no dar el comando de prueba.
- 2026-10-22 · [planificación] La cuota del plan gratuito se agotó en dos modelos a mitad de fase → probar en el chat con el modelo simulado todo lo posible y reservar las llamadas reales para una sola batería y las roturas; planificar baterías en días distintos si hace falta.
- 2026-10-22 · [chats-IA] La IA supuso cómo devuelve una pestaña vacía la librería (`[]`) y era `[[]]`; el seed se paró a la primera → con una librería nueva, comprobar en el chat el comportamiento real en los bordes (vacío, una fila, celdas de menos) antes de que Sergio ejecute.
- 2026-10-22 · [aprendizaje] El banco de pruebas solo mostraba el nombre de las herramientas: un fallo intermitente de `-lite` (llamada a `send_customer_email` que lanzó una excepción) quedó sin diagnosticar porque no se repitió → en los bancos de prueba, imprimir argumentos y error de cada llamada fallida desde el principio.
- 2026-10-22 · [git] En la 3a se hizo un commit después de fusionar el PR y se quedó fuera de `main` (hizo falta un segundo PR) → hacer todos los commits, incluidas las notas de cierre, antes de abrir el PR; si algo llega tarde, PR nuevo de la misma rama.
- 2026-10-23 · [entorno] Variables nuevas de `.env` que faltaron al probar (`EMAIL_TEST_RECIPIENT`, `NOTIFY_MODE`) → al añadir variables, dar el bloque completo para `.env` y, en el mismo paso, el comando que comprueba que están (`Select-String -Pattern '_MODE'`), sin mostrar secretos.
- 2026-10-23 · [chats-IA] Mensajes escritos por la IA que confundieron: la pista del 401 mencionaba el destinatario y las tablas de "lo esperado" no decían que eran para una ejecución normal → un mensaje de error por causa (no agrupar códigos) y toda tabla de "esperado" dice en qué escenario aplica.
- 2026-10-23 · [aprendizaje] Ritmo demasiado rápido: varias tareas seguidas con mucho texto, términos dados por sabidos (cabecera, cuerpo, ejemplo en `/docs`) y varias pruebas en un mensaje → Sergio se perdió varias veces y pidió ir paso a paso. Una acción por mensaje cuando hay que ejecutar algo, y describir dónde se ve cada cosa en pantalla la primera vez.
- 2026-10-23 · [chats-IA] Se repitió lo del 2026-10-22: en la propuesta de la T2 iba el comando de prueba y Sergio lanzó uvicorn antes de que existiera `main.py` → en la propuesta, ningún comando; los comandos solo cuando el cambio ya está hecho.
- 2026-10-23 · [entorno] Al editar `.env` se truncó `EMAIL_TEST_RECIPIENT` sin darse cuenta (Resend 422) → tras tocar `.env`, comprobar la forma de los valores sensibles (sin mostrarlos) antes de una prueba real.
- 2026-10-25 · [chats-IA] "Una acción por mensaje" se volvió lento en formularios largos (Render) y Sergio pidió ir más rápido → agrupar por pantalla (todos los campos de una pantalla en una tabla) y pegar la configuración en bloque, cambiando solo lo distinto. "Paso a paso" significa una pantalla o un concepto, no un campo.
- 2026-10-24 · [chats-IA] Claude dio una falsa alarma (diff de archivo entero) porque su terminal no traduce CRLF/LF como el Git de Windows de Sergio → antes de alarmar por un diff, compararlo con `--ignore-cr-at-eol` o `core.autocrlf=true`.
- 2026-10-25 · [planificación] La rotura 3 (canal de avisos en Render) se quedó sin ejecutar por tiempo y cuota → planificar las roturas que gastan LLM al principio del cierre, o probarlas antes sin LLM, y reservar cuota para el cierre.
