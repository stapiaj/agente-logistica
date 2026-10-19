# Método de trabajo

Principio: **la IA escribe el código; Sergio dirige, lee, entiende y depura.** No se aprende a escribir sintaxis de memoria; se aprende a pedir bien, juzgar lo que se recibe y saber qué pasa cuando algo falla.

## En cada pieza

1. **Concepto primero.** Claude explica brevemente el concepto nuevo y para qué sirve en el proyecto. Sergio lo resume con sus palabras.
2. **Plan corto.** Claude dice qué archivos va a crear o tocar y por qué (3-5 líneas). Sergio da el visto bueno o lo cambia.
3. **Cambios pequeños.** Un archivo o una función cada vez, no "todo el proyecto de golpe".
4. **Sergio revisa en VS Code.** Lee el código y pregunta todo lo que no sepa explicar. Regla: **no se acepta código que no se entienda.**
5. **Sergio ejecuta.** Claude le da el comando exacto (PowerShell) y Sergio cuenta qué ha pasado.
6. **Ante un error:** Sergio intenta interpretarlo primero; después lo resuelven juntos.

## Al cerrar cada fase

1. **Romper algo a propósito** (lista en `docs/contexto/03-plan-fases.md`) y leer el error.
2. **Preguntas de repaso**: Claude hace 3 preguntas y da feedback a las respuestas.
3. **Actualizar `docs/estado/progreso.md`**: fase completada, decisiones, aprendizajes y pendientes.
4. **Commit** con un mensaje claro en inglés (p. ej. `feat: agent loop with mock tools`).

## Coordinación entre chats

Cada chat sigue el **protocolo obligatorio** de `docs/contexto/00-instrucciones-proyecto.md`: leer el estado al empezar, anotar la tarea en "Trabajo en curso" antes de cada cambio, registrar las decisiones después y dejar una entrada en `docs/estado/bitacora.md` antes de cerrar.

## Prueba final de aprendizaje

Sergio puede explicar el proyecto completo en 2 minutos, dibujar la arquitectura de memoria, responder "¿y si…?" sobre cualquier pieza y, con ayuda de la IA, reconstruir una parte desde cero sabiendo lo que hace.
