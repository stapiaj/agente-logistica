# Documentación

- `contexto/` → **diseño fijo**: protocolo, contexto, arquitectura, plan, método y modelo de datos. Es el contexto del proyecto de Claude. Solo cambia si se modifica el diseño (y entonces hay que avisar y registrarlo en `estado/progreso.md`).
- `estado/` → **estado vivo**: `progreso.md` (dónde estamos y trabajo en curso), `bitacora.md` (una entrada por sesión), `proximo-encargo.md` (el siguiente encargo preparado) y `lecciones.md` (aprendizajes sobre el método, para mejorar futuros proyectos). Cada chat lo lee al empezar y lo actualiza al trabajar.
  - Las tres primeras son notas de trabajo: se llevan en la carpeta local y no se publican (están en `.gitignore`). En este repo solo está `lecciones.md`.
