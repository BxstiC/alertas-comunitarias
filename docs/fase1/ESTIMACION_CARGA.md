# Estimación de carga y justificación del patrón de lectura/escritura

## 1. Estimación de carga

La naturaleza del problema indica que el sistema tendrá una proporción alta de lecturas respecto a escrituras. Un aviso comunitario suele publicarse una sola vez, pero puede ser consultado muchas veces por distintos vecinos a lo largo del día.

### Suposición base

- 1 publicación = 1 aviso nuevo
- 10 lecturas por cada aviso publicado
- Proporción esperada: 10:1 en favor de la lectura

### Ejemplo de escenario inicial

- Se publican 20 avisos al día.
- Cada aviso puede ser consultado unas 10 veces, en promedio.
- Entonces, la carga estimada sería:
  - Escrituras: 20 avisos/día
  - Lecturas: aproximadamente 200 consultas/día

En un entorno real, la carga de lectura puede ser mucho mayor si:

- hay distintas categorías activas,
- los vecinos revisan varias veces la misma información,
- la comunidad es numerosa,
- el sistema se usa de forma repetida durante emergencias o eventos puntuales.

### Cálculo de almacenamiento estimado a 5 años

**Supuestos de datos:**
- Un aviso promedio en texto plano (título, descripción corta, metadatos) pesa aproximadamente 2 KB.
- Estimamos un sobrecosto de base de datos (índices, logs de transacciones) del 50%, lo que nos da 3 KB por registro.

**Cálculo a 5 años:**
- Total de avisos: 5 avisos/día × 365 días/año × 5 años = 9.125 avisos.
- Almacenamiento neto de avisos: 9.125 avisos × 3 KB/aviso = 27.375 KB.
- Total en MB: 27.375 KB / 1024 = **26.7 MB** de almacenamiento estimado a 5 años.

Este volumen ínfimo confirma que el sistema está completamente dominado por la carga de red (lecturas) y no por la capacidad de almacenamiento, justificando plenamente una arquitectura ligera con réplicas.

### Conclusión

- La plataforma no necesita un patrón de carga equilibrado.
- Tiene un perfil claramente orientado a lectura.
- Esto justifica la necesidad de una réplica de lectura para atender las consultas sin saturar la base primaria.

## 2. Justificación del patrón de lectura/escritura

El patrón de uso esperado para esta solución es:

- escritura poco frecuente,
- lectura frecuente y repetida.

Esto responde al caso de avisos vecinales:

- Un vecino publica un aviso de corte de agua, pérdida de objetos o actividad comunitaria.
- Ese aviso es registrado una sola vez.
- Sin embargo, muchos vecinos consultan la plataforma varias veces para ver si el aviso sigue vigente, confirmar detalles o buscar información adicional.

Por tanto, la arquitectura debe diseñarse con la siguiente lógica:

- La base primaria se usa para las operaciones de escritura:
  - crear aviso
  - actualizar aviso si aplica
  - eliminar o invalidar datos si es necesario
- La réplica se usa para las operaciones de lectura:
  - listar avisos
  - consultar detalle
  - visualizar avisos recientes
  - consultar información ya publicada

Esta separación tiene varias ventajas:

- reduce la carga sobre la base primaria,
- mejora la velocidad de respuesta en consultas,
- evita que el tráfico de lectura afecte el rendimiento de las escrituras,
- cumple con el objetivo de demostrar un diseño basado en alta proporción de lecturas.

Por lo tanto, la justificación técnica del uso de réplica es sólida: el sistema está pensado para servir gran cantidad de lecturas y pocas escrituras, y esta arquitectura permite escalar de forma más eficiente y mantener la distribución de carga adecuada.

## 3. Impacto en la arquitectura

La separación entre lectura y escritura es una decisión clave para esta solución porque:

- la mayoría de usuarios interactúan como consultantes,
- la frecuencia de consultas supera claramente la frecuencia de publicaciones,
- la base primaria queda priorizada para transacciones de escritura,
- la réplica asegura disponibilidad y baja latencia para la lectura.

Esto encaja con el objetivo del proyecto: ofrecer una plataforma simple, rápida y trazable para la comunidad vecinal.

