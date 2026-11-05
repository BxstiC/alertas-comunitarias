# Requisitos funcionales y no funcionales

## 1. Requisitos funcionales del sistema (Máximo 8)

1. **RF-01:** El sistema debe listar los avisos comunitarios vigentes.
2. **RF-02:** El sistema debe permitir publicar nuevos avisos con título, descripción, categoría y fecha.
3. **RF-03:** El sistema debe mostrar el detalle completo de un aviso seleccionado.
4. **RF-04:** El sistema debe filtrar/diferenciar avisos según su categoría.
5. **RF-05:** Las operaciones de creación (escrituras) deben enviarse exclusivamente a la base de datos primaria (X-DB: primary).
6. **RF-06:** Las operaciones de consulta (lecturas) deben resolverse exclusivamente desde la réplica (X-DB: replica).
7. **RF-07:** Toda respuesta HTTP debe incluir la cabecera `X-Instance` para identificar el contenedor que la procesó.
8. **RF-08:** Toda respuesta HTTP debe incluir la cabecera `X-DB` para identificar la base de datos utilizada.

### Casos de uso principales

- CU-01: Consultar avisos recientes.
  - El vecino accede a la plataforma y visualiza los avisos publicados.
- CU-02: Ver detalle de un aviso.
  - El vecino selecciona un aviso y consulta sus datos completos.
- CU-03: Publicar un aviso.
  - El vecino introduce los datos del aviso y lo registra en la comunidad.
- CU-04: Comprobar trazabilidad de la solicitud.
  - El desarrollador o evaluador verifica que `X-Instance` y `X-DB` reflejan la instancia y base que atendieron la operación.
- CU-05: Validar lectura/escritura en arquitectura.
  - Se comprueba que una escritura va a la base primaria y una lectura va a la réplica.

## 2. Requisitos no funcionales (Objetivos medibles)

- **Latencia objetivo:** Las consultas de lectura (`GET /avisos`) deben responder en menos de 500 ms. Las escrituras (`POST /avisos`) deben responder en menos de 1 segundo.
- **Disponibilidad:** El sistema debe mantener su capacidad de respuesta (lecturas) si una de las instancias de la aplicación cae.
- **RPO (Recovery Point Objective):** Máximo 5 minutos. Se acepta la pérdida de los avisos publicados en los últimos 5 minutos ante una falla catastrófica de la primaria no replicada.
- **RTO (Recovery Time Objective):** Máximo 30 minutos para restaurar el flujo de publicación (escrituras) promoviendo la réplica o levantando una nueva base primaria.

## 3. Criterios de aceptación

- Un vecino puede abrir la aplicación y ver los avisos más recientes.
- Un vecino puede publicar un aviso con los datos mínimos requeridos.
- Un aviso se muestra con título, descripción, categoría y fecha.
- La respuesta HTTP incluye `X-Instance` y `X-DB`.
- Las lecturas se atienden desde la réplica y las escrituras desde la primaria.
- La interfaz se considera usable para una comunidad vecinal con poca complejidad técnica.
