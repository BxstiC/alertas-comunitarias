# Bitácora · ISI601 Proyecto individual

Por cada clase: qué hice hoy, dónde me trabé y qué haré la próxima clase. Cuando usé IA, qué le pedí y qué decidí yo.

## Mié 4 nov
- **Qué hice:** creé el repositorio y elegí la problemática (alertas comunitarias vecinales); subí la documentación inicial.
- **Dónde me trabé:** justificar la proporción de 10 lecturas por escritura como un comportamiento real y no solo como un supuesto de prueba.
- **Qué haré la próxima clase:** requisitos y estimación de carga.
- **IA:** pedí revisar `PROBLEMA.md`; decidí acotar el alcance a 2 entidades (`Categorias` y `Avisos`) y justificar el 10:1 con consultas repetidas ante cortes de servicio.

## Jue 5 nov
- **Qué hice:** REQUISITOS.md y ESTIMACION_CARGA.md con la justificación de la relación lecturas/escrituras.
- **Dónde me trabé:** me pasé del máximo de 8 requisitos funcionales y faltaban métricas exactas de latencia, RPO y RTO.
- **Qué haré la próxima clase:** borrador de los diagramas lógico y físico.
- **IA:** pedí validar los requisitos y cálculos; decidí reducir a 8 requisitos funcionales, fijar RPO de 5 min / RTO de 30 min y calcular el almacenamiento a 5 años (~26,7 MB).

## Vie 6 nov
- **Qué hice:** diagramas lógico y físico en draw.io y PNG.
- **Dónde me trabé:** conecté cada instancia a una sola base en vez de ambas a las dos, y faltaba marcar los puntos únicos de falla (SPOF).
- **Qué haré la próxima clase:** documento de diseño final y presentación de la Fase 1.
- **IA:** pedí revisar los diagramas; decidí conectar `app-1` y `app-2` tanto a primaria como a réplica y marcar en rojo el gateway, balanceador y primaria como SPOF.

## Mié 11 nov · Entrega Fase 1
- **Qué hice:** consolidé `DISENO.md` con los diagramas finales en PNG, armé la presentación `.pptx` y subí la entrega con el tag `fase-1`.
- **Dónde me trabé:** ajustar los flujos en los diagramas para que ambas instancias (`app-1` y `app-2`) apuntaran tanto a la primaria como a la réplica sin que se superpusieran las etiquetas, además de marcar los puntos únicos de falla (SPOF).
- **Qué haré la próxima clase:** levantar primaria y réplica con Docker Compose.
- **IA:** pedí revisar la coherencia de los diagramas contra la rúbrica; decidí resaltar en rojo el gateway, el balanceador y la primaria como SPOF y agregar las alternativas tecnológicas en `DISENO.md`.

## Jue 12 nov
- **Qué hice:** configuré `docker-compose.yml` con PostgreSQL 16 (primaria y réplica por streaming), balanceador NGINX y 2 instancias de prueba.
- **Dónde me trabé:** sincronizar el arranque de la réplica para que esperara a que la primaria creara el usuario `replicator`.
- **Qué haré la próxima clase:** gateway, balanceador y evidencias de la Fase 2.
- **IA:** pedí los scripts `primary-init.sql`, `replica-init.sh` y `nginx.conf`; decidí usar `healthcheck` en la primaria y separar las redes en `proxy` y `data`.

## Vie 13 nov · Entrega Fase 2
- **Qué hice:** docker-compose.yml con gateway (Traefik + api-key-auth), balanceador NGINX, app-1/app-2, primaria y réplica; EVIDENCIAS.md.
- **Dónde me trabé:** validar que Traefik cortara peticiones sin API key (401) y con exceso de tráfico (429) antes de pasarlas a NGINX.
- **Qué haré la próxima clase:** aplicación real y pruebas de falla.
- **IA:** pedí comandos `curl` y revisión de `EVIDENCIAS.md`; decidí no exponer puertos internos al host (solo puerto 8000 en Traefik) y etiquetar `fase-2`.

## Mié 18 nov
- **Qué hice:** programé la aplicación real en FastAPI (`app.py`) con `asyncpg` conectada a la primaria (`POST`) y a la réplica (`GET`).
- **Dónde me trabé:** evitar que `app-1` y `app-2` chocaran al intentar crear la tabla `avisos` al mismo tiempo al iniciar.
- **Qué haré la próxima clase:** probar todo el flujo real, corregir errores de replicación y documentar fallas.
- **IA:** pedí implementar los endpoints y validación en `app.py`; decidí usar un lock en PostgreSQL para crear la tabla solo en primaria, pool de solo lectura para réplica y middleware para `X-Instance` y `X-DB`.

## Jue 19 nov
- **Qué hice:** verifiqué POST (X-DB: primary), lecturas (X-DB: replica), API key (401) y límite de peticiones (429) por el gateway; corregí la réplica, que no replicaba; subí las fases 2 y 3 al repositorio; probé todo desde un clon limpio.
- **Dónde me trabé:** la réplica estaba "desconectada": su volumen guardaba el host antiguo (`db-primary`) y el `.pgpass` ya tenía `db-primary-repl`, así que se conectaba sin contraseña.
- **Qué haré la próxima clase:** completar esta bitácora, etiquetas fase-1/2/3 y ensayar la presentación.
- **IA:** usé Claude Code para revisar que funcionara, encontrar el error de la réplica y auditar el repositorio. Decidí recrear la sincronización limpia de la réplica contra el host correcto, conservar el historial de commits del repositorio y documentar las mediciones de RPO y RTO.

## Vie 20 nov · Entrega Fase 3
- **Qué hice:** revisé `PRUEBAS_DE_FALLA.md` y `README.md` final, completé la bitácora y apliqué la etiqueta `fase-3`.
- **Dónde me trabé:** sin bloqueos; todo levantó limpio con `docker compose up -d`.
- **Qué haré la próxima clase:** presentación final.
- **IA:** pedí a Claude Code un guion de comandos para la demostración en vivo; decidí repasar el código de `app.py`, `nginx.conf` y PostgreSQL para explicarlo y modificarlo sin ayuda en la defensa.
## Mar 24 nov · Ajustes antes de la entrega de la Fase 3
- **Qué hice:** revisé el proyecto contra el enunciado y corregí los puntos débiles: estimación en lecturas/escrituras por segundo (promedio, hora punta y pico de emergencia) para una escala objetivo de 10.000 vecinos; disponibilidad 99,5 %; tres tipos de cliente (web, app móvil y sistema municipal) con una API key cada uno y límite de peticiones por cliente; `docker-compose.yml` en la raíz para levantar todo con un solo comando; renombré `DISEÑO.md` a `DISENO.md` como pide el enunciado.
- **Dónde me trabé:** la estimación anterior (5 avisos/día) no justificaba el balanceador; con los números quedó claro que 2 instancias se justifican por disponibilidad y crecimiento, no por volumen.
- **Qué haré la próxima clase:** presentación final; ensayar la demo clonando el repositorio en un equipo del laboratorio.
- **IA:** usé Claude Code para revisar el repositorio contra el PDF del enunciado e implementar los cambios. Decidí yo la escala objetivo (comuna de 10.000 vecinos) y los tres clientes; lo probé levantando todo desde la raíz y corriendo la demo (401 sin key, 429 en la web mientras la app móvil sigue pasando).

## Mié 25 nov · Presentación y cierre de la Fase 3
- **Qué hice:** saqué capturas reales de la consola de cada falla (apagar una instancia, cortar la réplica y failover, con RTO 12,6 s y RPO 0) y las agregué a `PRUEBAS_DE_FALLA.md` junto con el CSV de esa corrida; corregí un dato que había quedado de la estimación antigua (la carga extra de la primaria cuando cae la réplica) y preparé la carpeta de entrega.
- **Dónde me trabé:** se terminó el tiempo en la sala antes de sacar la captura del failover, así que la terminé en casa. Por eso las capturas tienen horas distintas.
- **Qué haré a continuación:** entregar el repositorio con la etiqueta `fase-3`.
- **IA:** usé Claude Code para ejecutar las pruebas, sacar las capturas de la consola y actualizar los documentos. Yo decidí agregar las capturas a la entrega y qué fallas mostrar.
