# Contexto: por qué existe este proyecto

## Motivación

Proyecto personal. Me interesa cómo los agentes de IA pasan de una demo a trabajar dentro de los procesos reales de una organización, y quería aprender a construir uno de punta a punta: LLMs desde código, tool calling, integraciones con sistemas reales, webhooks, despliegue y operación. Con buenas prácticas y entendiendo cada decisión, no solo que funcione.

Objetivos:

1. **Aprender haciendo** las piezas de un agente en producción.
2. **Construir algo que funcione de punta a punta**, desplegado y con datos inventados.
3. **Saber explicar cada pieza**: cada fase se cierra rompiendo algo a propósito y con preguntas de repaso.

## Qué es un "AI worker"

Un agente que no solo conversa: ejecuta un proceso de principio a fin dentro de los sistemas de una organización (leer datos, decidir, enviar emails, avisar a personas y dejar registro). Este proyecto construye uno pequeño para un caso concreto.

## El caso de negocio (como si fuera un cliente)

**Cliente ficticio:** un operador logístico mediano.

**Proceso actual:** cuando un envío se retrasa, una persona de atención al cliente lo detecta en el sistema, busca los datos del cliente, redacta un email y, si el cliente es importante o el retraso es grave, avisa a su responsable. Es manual, lento e inconsistente.

**Solución:** un agente que reacciona en cuanto un envío pasa a "retrasado", consulta los datos, decide qué hacer según unas reglas de negocio, informa al cliente, escala a un humano cuando hace falta y deja registro de todo.

**Impacto a contar:** tiempo de respuesta de horas a segundos, tono y criterios homogéneos, el equipo humano solo atiende los casos que lo merecen y trazabilidad completa.

**Siguientes casos de uso (para la sección "roadmap"):** llamada de voz al cliente, confirmación de citas de entrega, reclamación al transportista y cobros de facturas vencidas.
