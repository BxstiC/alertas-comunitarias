# Estimación de carga y justificación del patrón de lectura/escritura

## 1. Estimación de carga

La naturaleza del problema indica que el sistema tendrá una proporción alta de lecturas respecto a escrituras. Un aviso comunitario suele publicarse una sola vez, pero puede ser consultado muchas veces por distintos vecinos a lo largo del día.

Se estiman dos escenarios: un **piloto** en una junta de vecinos y la **escala objetivo**, una comuna completa, que es para la que se dimensiona la arquitectura.

### Supuestos explícitos

| Supuesto | Piloto | Escala objetivo |
|---|---|---|
| Vecinos registrados | 500 | **10.000** (comuna mediana) |
| Vecinos activos al día | 30 % → 150 | 30 % → **3.000** |
| Lecturas por vecino activo al día (lista + 2 a 4 detalles) | 5 | 5 |
| Avisos publicados al día (vecinos + municipio) | 5 | **100** (80 de vecinos y 20 automáticos del municipio) |
| Tráfico concentrado en la hora punta (19:00–20:00) | 20 % del día | 20 % del día |
| Pico de emergencia (p. ej. corte de agua masivo) | — | los 3.000 activos consultan 3 veces en 10 minutos |
| Tamaño de un aviso con índices y metadatos | 3 KB | 3 KB |

### Lecturas y escrituras

**Por día:**

- Piloto: 150 × 5 = **750 lecturas/día** y **5 escrituras/día** → relación 150:1.
- Escala objetivo: 3.000 × 5 = **15.000 lecturas/día** y **100 escrituras/día** → relación **150:1**.

**Por segundo, escala objetivo:**

| Momento | Lecturas/s | Escrituras/s | Cálculo |
|---|---|---|---|
| Promedio (24 h) | **0,17** | **0,0012** (≈ 1 cada 14 min) | 15.000 / 86.400 · 100 / 86.400 |
| Hora punta | **0,83** | **0,0056** (≈ 1 cada 3 min) | 20 % → 3.000 / 3.600 · 20 / 3.600 |
| Pico de emergencia (10 min) | **15** | **0,05** (30 avisos en 10 min) | 3.000 × 3 / 600 · 30 / 600 |

La relación de lecturas a escrituras se mantiene muy por sobre 10:1 en todos los casos (150:1 en promedio y 300:1 en una emergencia). Justo en una emergencia es cuando más se lee y cuando el servicio no puede caerse.

### Qué significan estos números para la arquitectura

- **Réplica de lectura:** con 150:1, más del 99 % de las consultas a la base son lecturas. La réplica las absorbe y la primaria queda libre para las escrituras.
- **Balanceador y 2 instancias:** 15 lecturas/s las atiende una sola instancia de FastAPI. El balanceador no se justifica por el volumen actual, sino por **disponibilidad** (si cae una instancia en plena emergencia, la otra sigue respondiendo) y por **crecimiento** (si el sistema se extiende a 10 comunas, el pico llega a ~150 lecturas/s y basta con agregar instancias detrás del mismo balanceador).
- **Límite de peticiones del gateway:** en la demo es de 10 req/s por cliente, con ráfaga de 20, para poder mostrar el 429. Con la escala objetivo, el cliente web debería tener al menos 50 req/s para cubrir el pico de emergencia (15 lecturas/s) con margen.

### Almacenamiento a 5 años

- Piloto: 5 avisos/día × 365 × 5 = 9.125 avisos × 3 KB = 27.375 KB ≈ **26,7 MB**.
- Escala objetivo: 100 avisos/día × 365 × 5 = **182.500 avisos** × 3 KB = 547.500 KB / 1.024 ≈ **535 MB**.

Medio gigabyte en 5 años cabe en cualquier servidor. El sistema está dominado por la cantidad de lecturas, no por el almacenamiento, y eso refuerza el uso de una réplica de lectura.

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
