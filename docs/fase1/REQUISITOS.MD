# Requisitos funcionales y no funcionales

## 1. Requisitos funcionales

La plataforma debe permitir a los vecinos:

- Consultar avisos comunitarios recientes desde un único punto de acceso.
- Publicar avisos con la siguiente información mínima:
  - título
  - descripción
  - categoría
  - fecha
- Visualizar el detalle de cada aviso al seleccionarlo desde la lista.
- Diferenciar avisos por categoría, por ejemplo: cortes de servicio, objetos perdidos, seguridad, actividades o avisos generales.
- Consultar avisos tanto recientes como históricos que sigan siendo relevantes.
- Verificar qué instancia de aplicación y qué base de datos atendieron cada solicitud mediante las cabeceras X-Instance y X-DB.
- Separar de forma explícita la operación de escritura y la de lectura para evidenciar el flujo hacia la base primaria y la réplica, respectivamente.

### Requisitos funcionales del sistema

- RF-01: El sistema debe listar los avisos comunitarios disponibles.
- RF-02: Cada aviso debe incluir título, descripción, categoría y fecha.
- RF-03: El usuario debe poder publicar un nuevo aviso.
- RF-04: El sistema debe permitir consultar el detalle completo de un aviso.
- RF-05: El sistema debe clasificar los avisos por categoría.
- RF-06: El sistema debe mostrar avisos vigentes o recientes en la vista principal.
- RF-07: Cada respuesta debe incluir identificadores de instancia y base de datos mediante X-Instance y X-DB.
- RF-08: Las operaciones de escritura deben dirigirse a la base primaria.
- RF-09: Las operaciones de lectura deben dirigirse a la réplica.
- RF-10: El sistema debe evitar la dispersión de información entre canales no centralizados.

### Casos de uso principales

- CU-01: Consultar avisos recientes.
  - El vecino accede a la plataforma y visualiza los avisos publicados.
- CU-02: Ver detalle de un aviso.
  - El vecino selecciona un aviso y consulta sus datos completos.
- CU-03: Publicar un aviso.
  - El vecino introduce los datos del aviso y lo registra en la comunidad.
- CU-04: Comprobar trazabilidad de la solicitud.
  - El desarrollador o evaluador verifica que X-Instance y X-DB reflejan la instancia y base que atendieron la operación.
- CU-05: Validar lectura/escritura en arquitectura.
  - Se comprueba que una escritura va a la base primaria y una lectura va a la réplica.

## 2. Requisitos no funcionales

Los requisitos no funcionales que debe cumplir la solución son los siguientes:

### Rendimiento

- La plataforma debe estar optimizada para un patrón de lectura intensiva.
- La lectura debe ser más rápida y escalable que la escritura.
- La solución debe soportar un volumen mayor de consultas que de publicaciones.

### Escalabilidad

- El sistema debe permitir aumentar la capacidad de lectura sin afectar significativamente la escritura.
- La separación entre primaria y réplica debe facilitar la ampliación de la carga de consultas.

### Trazabilidad

- Cada solicitud debe indicar qué instancia atendió la petición y qué base de datos la gestionó.
- Esto permite validar el comportamiento de la arquitectura y facilitar diagnóstico.

### Simplicidad de uso

- La interfaz debe ser accesible para usuarios sin experiencia técnica.
- La publicación y consulta de avisos debe ser intuitiva.

### Fiabilidad

- La información publicada debe estar disponible de manera consistente para los vecinos.
- El sistema debe reducir la posibilidad de avisos duplicados o información no visible.

### Mantenibilidad

- La arquitectura debe separar claramente la lógica de lectura y escritura.
- Esto facilita pruebas, evolución y análisis de rendimiento.

### Seguridad básica

- Las peticiones deben ser trazables y la infraestructura debe permitir control de autenticación y autorización en etapas posteriores, sin que esto sea requisito principal de la fase inicial.

## 3. Criterios de aceptación

- Un vecino puede abrir la aplicación y ver los avisos más recientes.
- Un vecino puede publicar un aviso con los datos mínimos requeridos.
- Un aviso se muestra con título, descripción, categoría y fecha.
- La respuesta HTTP incluye X-Instance y X-DB.
- Las lecturas se atienden desde la réplica y las escrituras desde la primaria.
- La interfaz se considera usable para una comunidad vecinal con poca complejidad técnica.
