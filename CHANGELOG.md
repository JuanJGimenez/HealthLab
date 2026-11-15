# Registro de cambios

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa
[versionado semántico](https://semver.org/lang/es/).

## [0.3.0] - 2026-11-15

Etapa 2b del plan: capa de transformación. La app ya convierte una exportación completa en las
tablas limpias del diccionario de datos, con horas locales, unidades conocidas y validaciones de
contenido. Todavía no guarda nada en la base.

### Agregado

- `reading.source`: un único objeto que da acceso a las tablas, los archivos de detalle y la
  fecha de una exportación.
- `transform.common`: piezas compartidas: conversión de horas y husos, lectura de archivos de
  detalle, validaciones y registro de cada dato rechazado u observado.
- `transform.sleep`, `transform.oxygen`, `transform.night_signals`, `transform.heart` y
  `transform.activity`: quince dominios que producen veinte tablas.
- `transform.export`: transforma la exportación entera, dominio por dominio; si uno falla, lo
  registra y sigue con los demás.

### Comprobado con datos reales

- Exportación de septiembre de 2026 contra la base del prototipo: las 14 tablas comparables
  coinciden en cantidad de filas y en valores.
- Exportación de noviembre de 2026: 20 tablas y 2,8 millones de filas en 36 segundos, sin dominios
  fallidos. 13 observaciones de validación: 6 sesiones de sueño sin duración, 4 ronquidos y 1
  registro de variabilidad fechados en 1970, 1 noche sin medición de respiración y 1 archivo de
  detalle vacío.

### Corregido respecto del prototipo

- Las series por minuto se identifican por el momento en UTC. Identificarlas por hora local
  descartaba minutos reales registrados durante un viaje con cambio de huso.
- Las ventanas de variabilidad cardíaca usan el huso de su propio registro, no un huso fijo.

## [0.2.0] - 2026-11-15

Etapa 2a del plan: capa de lectura. La app ya abre y lee una exportación real completa, y compara
su estructura con los contratos. Todavía no transforma ni guarda datos.

### Agregado

- `reading.archive`: abre una exportación desde un zip, su carpeta o una carpeta que la contiene.
  Rechaza un zip cuyas entradas intentan escribir fuera de la carpeta de trabajo.
- `reading.tables`: lista las tablas con la versión de Samsung Health y de esquema de cada una, y
  las lee como texto, sin prefijos en los nombres de columna.
- `reading.details`: lee los archivos de detalle (series por minuto o por intervalo).
- `reading.compatibility`: informe de compatibilidad contra los contratos, con tres niveles:
  error, advertencia e información.
- `reading.errors`: errores propios de la lectura.

### Comprobado con datos reales

- Exportación de noviembre de 2026: 59 tablas y 161.387 filas leídas sin errores, con la misma
  cantidad de filas por tabla que registran los contratos. Los 54.196 archivos de detalle de las
  tablas en uso se leen sin problemas. El informe de compatibilidad no tiene hallazgos.
- Exportación de septiembre de 2026: el informe reproduce lo hallado a mano en la etapa 0:
  23 columnas que entonces no existían, 8 tablas con versión de esquema anterior y 1 tabla ausente.

### Cambiado

- El proyecto requiere Python 3.12 o superior (decisión 28).

## [0.1.0] - 2026-11-14

Etapa 1 del plan de construcción: esqueleto del proyecto. Todavía no importa datos ni abre ventana.

### Agregado

- Estructura por capas en `src/misalud/`, con la responsabilidad de cada capa documentada.
- `config.py`: rutas de la app, umbrales de análisis y rangos de validación, cada uno con su motivo.
- Contratos de las 59 tablas de Samsung Health (`reading/contracts.json`) y su lector tipado.
- Exportación sintética para pruebas, con el mismo formato de archivos que Samsung Health.
- Pruebas automáticas, incluida una que hace cumplir la regla de dependencias entre capas.
- Herramientas de calidad: ruff (estilo y formato), mypy en modo estricto y pytest con cobertura.
- Documentos: arquitectura, diccionario de datos, reglas de fusión y registro de decisiones.
