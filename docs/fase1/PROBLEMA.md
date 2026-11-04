# Problema: alertas comunitarias vecinales

## Contexto

En una comunidad vecinal, la información sobre cortes de servicios, objetos
perdidos, actividades, situaciones de seguridad y otros avisos suele circular
por canales dispersos, como grupos de mensajería o publicaciones en redes
sociales. Esto dificulta encontrar avisos vigentes y consultar información
anterior, especialmente para quienes no participan en todos esos canales.

## Problema

Los vecinos no cuentan con un lugar centralizado donde consultar avisos
comunitarios recientes y sus detalles. Como resultado, pueden pasar por alto
información importante, recibir avisos duplicados o no saber si un aviso sigue
vigente. Quienes publican avisos tampoco tienen una forma sencilla de ponerlos
a disposición de toda la comunidad.

## Personas usuarias

- **Vecino consultante:** revisa los avisos disponibles para mantenerse
  informado.
- **Vecino que publica:** registra avisos relevantes para la comunidad.

## Objetivo del proyecto

Definir y construir una plataforma sencilla para que los vecinos publiquen,
consulten y revisen avisos comunitarios desde un punto centralizado.

## Alcance inicial

La plataforma permitirá:

- Consultar avisos comunitarios.
- Publicar un aviso con título, descripción, categoría y fecha.
- Identificar la instancia de aplicación y la base de datos que atendieron
  cada solicitud mediante las cabeceras `X-Instance` y `X-DB`.
- Separar las operaciones de escritura y lectura para demostrar el flujo hacia
  la base primaria y la réplica, respectivamente.

La primera versión se enfocará en la consulta y publicación de avisos. No
contemplará mensajería entre usuarios, geolocalización, notificaciones
automáticas ni moderación avanzada.

## Patrón de uso esperado

### Justificación del patrón de uso (alta proporción de lecturas)

La naturaleza de una alerta comunitaria implica que un vecino publica un aviso
(una escritura), mientras que decenas o cientos de vecinos pueden ingresar a la
plataforma para leerlo a lo largo del día (múltiples lecturas). Por ejemplo,
ante un aviso de corte de agua, este se registra una sola vez, pero muchos
vecinos consultan sus detalles y vuelven a revisar la página para conocer
actualizaciones. Por eso, se espera que haya al menos **10 lecturas por cada
escritura**. Esta proporción justifica el uso de una réplica de lectura, que
permite atender consultas sin enviar todas las lecturas a la base de datos
primaria, reservada para las escrituras.
