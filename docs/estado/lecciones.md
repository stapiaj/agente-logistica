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
