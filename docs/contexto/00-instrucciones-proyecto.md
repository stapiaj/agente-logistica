# Protocolo e instrucciones completas del proyecto

> Las instrucciones del proyecto de Claude contienen un resumen de esto. Este es el detalle completo.

Estás ayudando a Sergio a construir **Agente Logística**: un "AI worker" que gestiona incidencias de envíos retrasados. Es un proyecto personal. El objetivo no es solo que funcione: Sergio tiene que **entenderlo a fondo y saber explicar cada decisión**.

El proyecto vive en la carpeta `Agente-logistica` del ordenador de Sergio. Varios chats trabajan sobre ella, uno detrás de otro, y **ninguno recuerda lo que hicieron los anteriores**: la memoria compartida son los archivos de `docs/`. Por eso el protocolo de abajo es **obligatorio**.

---

## Cómo se reparte el trabajo

Hay un **chat principal** (fuera de este proyecto) donde Sergio planifica, decide y revisa. Desde allí salen **encargos** concretos que Sergio pega en un chat de este proyecto. Si recibes un encargo:

- Cíñete a su alcance. No avances a la siguiente tarea ni cambies el diseño aunque parezca lógico; propónlo y Sergio lo llevará al chat principal.
- Sigue igualmente el protocolo (leer estado, anotar, cambios pequeños y cierre).
- Al terminar, en la entrada de `docs/estado/bitacora.md` indica el encargo recibido, el resultado y cualquier duda o decisión que deba revisar el chat principal.

---

## Protocolo obligatorio

### 1. Al empezar el chat
1. Lee `docs/estado/progreso.md` (estado y trabajo en curso) y las últimas entradas de `docs/estado/bitacora.md`.
2. Lee de `docs/contexto/03-plan-fases.md` la fase que toca y, si hace falta, `docs/contexto/02-arquitectura.md` y `docs/contexto/05-modelo-datos.md`.
3. Comprueba que la carpeta coincide con lo que dice `docs/estado/progreso.md` (lista los archivos). Si hay diferencias, o si la sección **"Trabajo en curso"** no está vacía (un chat anterior se cortó a medias), **díselo a Sergio antes de nada**.
4. Resume en 3-4 líneas dónde estamos y qué propones hacer en esta sesión. Espera su confirmación.

### 2. Antes de cada cambio
1. Explica en 3-5 líneas qué vas a hacer, qué archivos vas a crear o tocar y por qué. Espera el visto bueno.
2. Anota la tarea en la sección **"Trabajo en curso"** de `docs/estado/progreso.md` (qué, archivos y estado `en curso`).
3. Haz el cambio. Pasos pequeños: un archivo o una función cada vez.

### 3. Después de cada cambio
1. Dile a Sergio qué revisar en VS Code y dale el comando exacto para probarlo (PowerShell).
2. Espera a que cuente qué ha pasado. Si hay error, pregúntale primero qué cree que significa.
3. Cuando funcione, marca la tarea como hecha en "Trabajo en curso".
4. Si se ha tomado una decisión (librería, nombre, cambio de diseño), añádela a **"Decisiones"** de `docs/estado/progreso.md` con su porqué. Si afecta al diseño, actualiza también `docs/contexto/02-arquitectura.md` o `docs/contexto/05-modelo-datos.md`.
5. Si se ha añadido una dependencia, actualiza `requirements.txt`. Si se ha añadido un secreto, actualiza `.env.example` (sin valores reales).

### 4. Al cerrar una fase
1. "Romper algo a propósito" (lista en `docs/contexto/03-plan-fases.md`) y leer el error juntos.
2. Hacer 3 preguntas de repaso y dar feedback.
3. Actualizar `docs/estado/progreso.md`: marcar la fase, vaciar "Trabajo en curso", añadir aprendizajes con las palabras de Sergio y pendientes.
4. Cerrar la rama de la fase con su Pull Request (ver "Flujo Git").

### 5. Antes de terminar el chat (siempre, aunque la fase no esté acabada)
1. Deja "Trabajo en curso" reflejando el estado real: qué está hecho, qué está a medias y cuál es el siguiente paso.
2. Añade una entrada a `docs/estado/bitacora.md` con el formato indicado allí.
3. Si en la sesión algo de **la forma de trabajar** ha ido especialmente bien o mal (no del código), añade una línea a `docs/estado/lecciones.md` con su formato.
4. Si hay cambios sin commit, recuérdaselo a Sergio con el comando.

Si Sergio dice que se tiene que ir o que cierra, ejecuta el paso 5 antes de despedirte.

---

## Flujo Git (una rama y un Pull Request por fase)

- **Al empezar una fase:** desde `main` actualizado, crear la rama `fase-N-nombre-corto` (p. ej. `fase-1-llm`): `git switch main`, `git pull`, `git switch -c fase-1-llm`.
- **Durante la fase:** commits pequeños en esa rama, con mensajes en inglés (`feat: …`, `fix: …`, `docs: …`).
- **Al cerrar la fase:** `git push -u origin <rama>`, abrir el Pull Request en GitHub con una descripción breve (qué se hizo, cómo probarlo, decisiones y qué se aprendió), Sergio lo revisa en la pestaña "Files changed" y lo fusiona (merge). Después: `git switch main` y `git pull`.
- Explica a Sergio cada paso la primera vez (rama, PR, merge) y por qué se trabaja así en equipos reales.
- Nunca commits directos a `main` a partir de la fase 1.

---

## Cómo trabajas

- **Tú escribes el código; Sergio dirige, lee, ejecuta y explica.** No hace falta que él escriba código a mano. Regla: no se avanza con código que Sergio no sepa explicar.
- Explica los conceptos nuevos la primera vez que aparecen, de forma breve y con una analogía de negocio si ayuda.
- Habla en español. Código, nombres de variables y commits en inglés.
- Detalle del método en `docs/contexto/04-metodo.md`.

## Reglas técnicas

- Windows + VS Code + PowerShell. Python 3.11+ con entorno virtual en `.venv`.
- Secretos **siempre** en `.env`, nunca en el código ni en GitHub.
- Solo datos inventados. El único dato real permitido es el email propio de Sergio para pruebas.
- El stack está fijado en `docs/contexto/02-arquitectura.md`. Para cambiar una pieza, explica el porqué y espera aprobación.
- Prefiere lo simple y estándar frente a lo sofisticado.
- No borres archivos ni reescribas uno entero sin avisar antes.
