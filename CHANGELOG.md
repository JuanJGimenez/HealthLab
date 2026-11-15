# Registro de cambios

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa
[versionado semántico](https://semver.org/lang/es/).

## [0.7.0] - 2026-11-15

Etapa 6a del plan: detalle de una noche y carga de etiquetas.

### Agregado

- Pantalla de una noche: encabezado con sus cifras, ocho pistas sobre el mismo eje de tiempo
  (etapas, oxígeno, pulso, variabilidad, ronquido, respiración, temperatura de piel y movimiento),
  cursor que cruza todas, zoom, franjas en los tramos con oxígeno bajo 90 % y flechas a la noche
  anterior y siguiente. Se abre con un clic en una noche desde gráficos y tablas.
- Elección de pistas: por defecto etapas, oxígeno, pulso y ronquido; la app recuerda la elección.
- `annotations`: ocho etiquetas iniciales de sí o no y una nota libre por fecha, editables desde
  la pantalla de una noche.
- Primera migración de esquema (versión 2): agrega las etiquetas iniciales.

### Corregido

- El detalle de oxígeno no viene siempre cada 10 minutos: 394 noches lo traen cada minuto. La
  métrica "intervalos bajo 85 %" mezclaba ambas cosas; ahora es "minutos bajo 85 %".

### Pendiente (etapa 6b)

- Comparar dos noches, filtro por etiqueta en todas las vistas, comparación con y sin etiqueta,
  color por etiqueta en Relacionar, carga desde el calendario y administración de etiquetas.

## [0.6.0] - 2026-11-15

Etapa 5 del plan: ventana y dashboard. La app ya se puede abrir: muestra las seis vistas
consultando la base en vivo, importa con vista previa y confirmación, y tiene el panel "Base de
datos". Disponible en español y en inglés.

### Agregado

- `interface.api`: los métodos que la página puede pedirle a Python.
- `interface.web`: la página con las vistas Oxígeno, Sueño, Corazón, Actividad, Relacionar y
  Datos, los filtros de período y de noches, el flujo "Actualizar datos" y el panel "Base de datos".
- `interface.i18n` y `interface.settings`: textos en dos idiomas y preferencias recordadas.
- `interface.window`: la ventana, con el comando `misalud`.
- `queries`: resumen general, noches con caída sostenida por día de la semana, mediana móvil,
  filtro de noches de viernes y sábado, exportación a CSV y resumen de validaciones.
- `derived`: horas dormidas por noche, y recálculo automático cuando cambia la definición de las
  tablas calculadas.
- Prueba de punta a punta de la página en un navegador real.

### Pendiente de comprobar

- La ventana en sí (pywebview sobre Windows) todavía no se abrió en una computadora con Windows.
  La página se probó en Chromium con la misma conexión a Python que usa la ventana.

## [0.5.0] - 2026-11-15

Etapa 4 del plan: tablas calculadas y consultas. Después de cada importación la app arma una fila
por noche y una por día, y ya puede responder las preguntas de las pantallas. Todavía no abre
ventana.

### Agregado

- `derived`: tablas `night` y `day`, recalculadas completas después de cada importación.
- `queries`: lista de noches y de días, resumen de oxígeno, peores noches, promedios por mes y por
  día de la semana, relación entre dos métricas con correlación de Spearman, y datos del panel
  "Base de datos".
- `exercise_custom_type`: nombres de los tipos de ejercicio creados por el usuario.
- `pipeline.importing`: recalcula `night` y `day` al confirmar una importación.

### Comprobado con datos reales

- Septiembre de 2026: `night` da las mismas 503 noches que el prototipo, con los mismos valores,
  salvo la variabilidad y el pulso de 8 noches registradas en otro huso.
- Noviembre de 2026: 563 noches y 624 días; recalcular tarda menos de un segundo y las consultas
  de todas las vistas juntas, 0,04 segundos.

### Corregido

- La variabilidad y el pulso nocturno de las noches registradas en otro huso se calculan sobre el
  horario correcto.
- Se rechazan los registros nocturnos que repiten el inicio y el fin de una noche ya registrada
  (12 de respiración).

## [0.4.0] - 2026-11-15

Etapa 3 del plan: base de datos y fusión. La app ya guarda una exportación en su base, fusiona
las siguientes sin perder nada y lleva el registro de cada importación. Todavía no calcula las
tablas `night` y `day` ni abre ventana.

### Agregado

- `storage.schema` y `storage.database`: esquema de la base, con versión y migraciones.
- `storage.merge`: vista previa y fusión con las cuatro reglas, en una sola transacción, con
  historial de valores reemplazados y registro de la importación.
- `storage.backup`: respaldo antes de fusionar, 2 respaldos conservados y restauración.
- `storage.exports`: guarda los zips originales y borra los que ya no hacen falta.
- `pipeline.importing`: la importación completa en dos pasos, vista previa y confirmación.
- `transform.export`: un dominio cuya tabla el informe de compatibilidad marca como incompatible
  no se transforma.

### Comprobado con datos reales

- Septiembre de 2026 sobre base vacía: 2.550.780 registros nuevos. Vista previa en 25 segundos,
  fusión en 3.
- Noviembre de 2026 encima: 284.230 registros nuevos, 2.550.780 sin cambios, ninguno actualizado.
  Respaldo previo automático.
- Septiembre otra vez, después de noviembre: nada que agregar ni cambiar.
- La base ocupa 233 MB.

### Corregido

- Las series por minuto de una noche traían 3 momentos repetidos dentro del mismo archivo de
  detalle; ahora se guarda uno solo.
- `merge_rules.md` decía que los pasos del día de la exportación llegaban cortados. El total del
  día, que es lo que se importa, ya estaba completo; lo que faltaba eran filas que no se usan.

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
