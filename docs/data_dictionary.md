# MiSalud: diccionario de datos, versión 1

Estado: borrador de la etapa 0, del 14 de noviembre de 2026.
Exportación de referencia: `samsunghealth_<usuario>_20261114105425` (Samsung Health 7013005).
Archivo hermano: `contracts.json`, con las 59 tablas de Samsung y sus 1.115 columnas tal como llegan.

Este documento describe las tablas de la base de MiSalud: qué es una fila, de qué archivo de Samsung sale,
cuál es su clave de fusión y qué significa cada columna. Los nombres de tablas y columnas van en inglés
(decisión 11). Todavía no existe código: es la especificación que la etapa 2 debe cumplir.

## Cómo leer las marcas

- **Verificado:** comprobado contra la exportación de referencia.
- **Supuesto:** interpretación razonable que la exportación no permite confirmar. Se revisa antes de usarla en un informe.
- **Derivado:** lo calcula MiSalud; no viene de Samsung.

## Convenciones generales

| Tema | Regla | Estado |
|---|---|---|
| Horas en los CSV | `start_time`, `end_time` vienen en UTC como texto. Cada fila trae `time_offset` (por ejemplo `UTC-0300`). | Verificado |
| Horas en los archivos de detalle | Milisegundos desde 1970 en UTC. No traen desfase: se usa el de la fila madre. | Verificado |
| Hora local | Toda columna `*_at` guarda hora local = UTC + desfase de la fila. El desfase se conserva en `utc_offset_min`. | Derivado |
| Desfases presentes | UTC-3 en 697 sesiones de sueño, UTC-4 en 10 y UTC-5 en 2. Nunca se asume un desfase fijo. | Verificado |
| Días | `day_time` es la medianoche del día local, escrita como texto. Se guarda como fecha en `day`. | Verificado |
| Fecha de una noche | `night_date` = fecha local del inicio del sueño menos 12 horas. Una noche iniciada a las 02:00 del sábado pertenece al viernes. | Derivado |
| Clave de Samsung | `datauuid`, presente en 59 de las 59 tablas y en todas las que usa MiSalud. Se guarda como `samsung_id`. Los identificadores de septiembre siguen intactos en noviembre, salvo en las tablas de ventana corta. | Verificado |
| Registros con fecha 1970 | 4 eventos de ronquido traen año 1970. Se rechazan por validación. | Verificado |
| Columnas de control | Toda tabla de detalle lleva `first_import_id` y `last_import_id`, que apuntan a `import_log`. | Derivado |

## 1. Tablas de detalle (se fusionan)

### sleep_session

Una fila por sesión de sueño ya agrupada, sea noche o siesta.
Origen: `com.samsung.shealth.sleep` y `com.samsung.shealth.sleep_combined`. Clave: `samsung_id`.

Reglas de agrupación, verificadas en el prototipo:
las filas con `integrated_id` son parciales ya fusionadas en otra sesión y se descartan;
las filas que comparten `combined_id` son fragmentos de una misma noche y se unen en una sola sesión,
cuyos puntajes se toman de `sleep_combined`.

| Columna | Tipo | Unidad | Origen | Estado |
|---|---|---|---|---|
| `samsung_id` | texto | | `datauuid`, o `combined_id` si la sesión agrupa fragmentos | Verificado |
| `start_at`, `end_at` | fecha y hora | local | `start_time`, `end_time` + `time_offset` | Verificado |
| `utc_offset_min` | entero | minutos | `time_offset` | Verificado |
| `night_date` | fecha | | Convención general | Derivado |
| `duration_min` | número | minutos | `sleep_duration`; suma de los fragmentos | Verificado |
| `fragment_count` | entero | | Cantidad de filas agrupadas | Derivado |
| `is_night` | sí o no | | `duration_min` mayor a 120 | Derivado |
| `score` | número | 0 a 100 | `sleep_score` | Verificado |
| `efficiency_pct` | número | % | `efficiency` | Verificado |
| `latency_min` | número | minutos | `sleep_latency`, que viene en milisegundos | Verificado |
| `cycles` | entero | | `sleep_cycle` | Verificado |
| `light_min`, `rem_min` | número | minutos | `total_light_duration`, `total_rem_duration` | Verificado |
| `physical_recovery`, `mental_recovery` | número | 0 a 100 | Mismo nombre | Verificado |
| `movement_awakening` | número | sin confirmar | `movement_awakening`; rango observado 0 a 100 | Supuesto |

No se importan las 40 columnas de pesos y factores internos del puntaje (`factor_01`…, `*_weight`, `*_score`).

### sleep_stage

Una fila por tramo de una etapa. Origen: `com.samsung.health.sleep_stage`. Clave: `samsung_id`.
63.487 filas en la exportación de referencia.

| Columna | Tipo | Unidad | Origen | Estado |
|---|---|---|---|---|
| `samsung_id` | texto | | `datauuid` | Verificado |
| `session_id` | texto | | `sleep_id` → `sleep_session.samsung_id`, pasando por el grupo | Verificado |
| `start_at`, `end_at` | fecha y hora | local | `start_time`, `end_time` | Verificado |
| `stage_code` | entero | | `stage`: 40001, 40002, 40003 o 40004 | Verificado |
| `duration_min` | número | minutos | `end_at` − `start_at` | Derivado |

### spo2_night

Una fila por medición nocturna de oxígeno. Origen: `com.samsung.shealth.tracker.oxygen_saturation`,
solo filas con `tag_id` = 31301. Clave: `samsung_id`. Las 18 filas con `tag_id` = 31000 son mediciones
puntuales hechas a mano y no entran en esta tabla.

| Columna | Tipo | Unidad | Origen | Estado |
|---|---|---|---|---|
| `samsung_id` | texto | | `datauuid` | Verificado |
| `start_utc` | fecha y hora | UTC | `start_time` | Verificado |
| `start_at`, `end_at` | fecha y hora | local | `start_time`, `end_time` | Verificado |
| `spo2_avg`, `spo2_min`, `spo2_max` | número | % | `spo2`, `min`, `max` | Verificado |
| `low_seconds` | número | segundos | `low_duration`: tiempo con SpO₂ bajo 90 % | Verificado |
| `coverage_pct` | número | % | `coverage_rate`; presente en el 78 % de las filas | Verificado |

`low_seconds` es mayor que cero en las 277 noches cuyo mínimo fue menor a 90 %, y cero en todas las demás.
Eso confirma el umbral de 90 %.

### spo2_interval

Una fila por intervalo de 10 minutos dentro de una noche. Origen: archivo `binning` de `spo2_night`.
Clave: `night_samsung_id` + `start_utc`. Unos 37 intervalos por noche; historia completa desde marzo de 2025.

| Columna | Tipo | Unidad | Origen | Estado |
|---|---|---|---|---|
| `night_samsung_id` | texto | | `spo2_night.samsung_id` | Verificado |
| `start_utc` | fecha y hora | UTC | `start_time` | Verificado |
| `start_at`, `end_at` | fecha y hora | local | `start_time`, `end_time` | Verificado |
| `spo2_avg`, `spo2_min`, `spo2_max` | número | % | `spo2`, `spo2_min`, `spo2_max` | Verificado |
| `is_irregular` | sí o no | | `isIrregular`; ausente en algunos archivos | Supuesto |

### skin_temperature y skin_temperature_minute

`skin_temperature`: una fila por noche. Origen: `com.samsung.health.skin_temperature`. Clave: `samsung_id`.

| Columna | Tipo | Unidad | Origen | Estado |
|---|---|---|---|---|
| `temperature_c` | número | °C | `temperature` | Verificado |
| `baseline_c` | número | °C | `baseline` | Verificado |
| `min_c`, `max_c` | número | °C | `min`, `max` | Verificado |
| `lower_bound_c`, `upper_bound_c` | número | °C | `lower_bound`, `upper_bound`: rango habitual según Samsung | Supuesto |

`skin_temperature_minute`: una fila por minuto. Origen: archivo `binning_data`. Clave: `night_samsung_id` + `start_utc`.
Columnas `start_utc`, `start_at`, `mean_c`, `min_c`, `max_c`. Verificado.

### respiratory_rate y respiratory_rate_minute

`respiratory_rate`: una fila por noche. Origen: `com.samsung.health.respiratory_rate`. Clave: `samsung_id`.

| Columna | Tipo | Unidad | Origen | Estado |
|---|---|---|---|---|
| `rate_avg` | número | respiraciones por minuto | `average`; 0 significa sin medición y se guarda vacío | Verificado |
| `lower_limit`, `upper_limit` | número | respiraciones por minuto | Mismo nombre | Verificado |
| `is_outlier` | sí o no | | `is_outlier` | Supuesto |

`respiratory_rate_minute`: una fila por minuto. Origen: archivo `binning_data`. Clave: `night_samsung_id` + `start_utc`.
Columnas `start_utc`, `start_at`, `rate`.
El 1,8 % de los minutos trae 0, que significa sin medición y se guarda como vacío. Verificado.

### hrv_window

Una fila por ventana de variabilidad cardíaca. Origen: archivo `binning_data` de `com.samsung.health.hrv`.
Clave: `start_utc`. El registro madre cubre una hora y cada ventana dura unos 5 minutos.

| Columna | Tipo | Unidad | Origen | Estado |
|---|---|---|---|---|
| `start_utc` | fecha y hora | UTC | `start_time` | Verificado |
| `start_at`, `end_at` | fecha y hora | local | `start_time`, `end_time` | Verificado |
| `rmssd_ms`, `sdnn_ms` | número | milisegundos | `rmssd`, `sdnn` | Verificado |

Las ventanas se superponen: cada una dura unos 5 minutos y empieza 30 segundos después de la anterior
(verificado en la etapa 2b). Sirven para promediar, no para sumar duraciones.

### heart_rate_minute

Una fila por minuto con pulso. Origen: archivo `binning_data` de `com.samsung.shealth.tracker.heart_rate`.
Clave: `start_utc`. El registro madre cubre una hora.

| Columna | Tipo | Unidad | Origen | Estado |
|---|---|---|---|---|
| `start_utc` | fecha y hora | UTC | `start_time` | Verificado |
| `start_at` | fecha y hora | local | `start_time` | Verificado |
| `heart_rate`, `heart_rate_min`, `heart_rate_max` | número | latidos por minuto | Mismo nombre | Verificado |

### stress

Una fila por medición de estrés. Origen: `com.samsung.shealth.stress`. Clave: `samsung_id`.
Columnas `start_at`, `score` (0 a 100), `score_min`, `score_max`. Verificado.
El archivo `binning_data` trae además el detalle por minuto con `level` y `flag`; no se importa en la versión 1.

### snoring_event

Una fila por evento de ronquido. Origen: `com.samsung.shealth.sleep_snoring`. Clave: `samsung_id`.

| Columna | Tipo | Unidad | Origen | Estado |
|---|---|---|---|---|
| `start_at`, `end_at` | fecha y hora | local | `start_time`, `end_time` | Verificado |
| `duration_s` | número | segundos | `duration`, que viene en milisegundos | Verificado |

No hay vínculo con la sesión de sueño: se une por ventana de tiempo.

### movement_minute

Una fila por minuto con nivel de movimiento, de día y de noche. Origen: archivo `binning_data` de
`com.samsung.health.movement`. Clave: `start_utc`. Historia completa desde enero de 2025.

| Columna | Tipo | Unidad | Origen | Estado |
|---|---|---|---|---|
| `start_utc` | fecha y hora | UTC | `start_time` | Verificado |
| `start_at` | fecha y hora | local | `start_time` | Verificado |
| `activity_level` | número | sin unidad conocida | `activity_level`; mediana 3, percentil 99 de 128 | Supuesto |

Sirve para comparar minutos entre sí. No indica posición corporal.

### exercise

Una fila por sesión grabada. Origen: `com.samsung.shealth.exercise`. Clave: `samsung_id`.

| Columna | Tipo | Unidad | Origen | Estado |
|---|---|---|---|---|
| `start_at`, `end_at` | fecha y hora | local | `start_time`, `end_time` | Verificado |
| `duration_min` | número | minutos | `duration`, que viene en milisegundos | Verificado |
| `type_code` | entero | | `exercise_type` | Verificado |
| `custom_id` | texto | | `custom_id` → `exercise_custom_type` | Verificado |
| `calorie_kcal` | número | kcal | `calorie` | Verificado |
| `distance_m` | número | metros | `distance` | Verificado |
| `mean_hr`, `max_hr`, `min_hr` | número | latidos por minuto | `mean_heart_rate`, `max_heart_rate`, `min_heart_rate` | Verificado |
| `mean_speed_mps` | número | metros por segundo | `mean_speed` | Supuesto |
| `vo2_max` | número | ml/kg/min | `vo2_max`; presente en una sola sesión | Verificado |

El pulso segundo a segundo de cada sesión está en el archivo `live_data`; no se importa en la versión 1.
Los archivos `additional` no traen series ni repeticiones.

### exercise_custom_type

Una fila por tipo de ejercicio creado por el usuario, por ejemplo CrossFit. Origen:
`com.samsung.shealth.exercise.custom_exercise`. Clave: `custom_id`. Columnas `name` y `created_at` (UTC).
Una sesión de un tipo propio trae `type_code` 0 y su `custom_id`. Verificado.

### ecg

Una fila por electrocardiograma. Origen: `com.samsung.health.ecg`. Clave: `samsung_id`. 18 filas.

| Columna | Tipo | Unidad | Origen | Estado |
|---|---|---|---|---|
| `start_at` | fecha y hora | local | `start_time` | Verificado |
| `mean_hr` | número | latidos por minuto | `mean_heart_rate` | Verificado |
| `classification_code` | entero | | `classification`: 1 en 13 registros, 0 en 1, vacío en 4 | Verificado |
| `sample_frequency_hz` | entero | Hz | `sample_frequency`: 500 | Verificado |
| `sample_count` | entero | | `sample_count`: 15.000, es decir 30 segundos | Verificado |
| `trace_file` | texto | | `chart_data`: trazado completo, presente en 14 de 18 | Verificado |

El significado de los códigos de clasificación (1 = ritmo sinusal, 0 = no concluyente) es un supuesto.

### weight

Una fila por medición. Origen: `com.samsung.health.weight`. Clave: `samsung_id`. 17 filas.
Columnas `measured_at`, `weight_kg`, `height_cm`, `body_fat_pct`, `skeletal_muscle_mass_kg`,
`basal_metabolic_rate_kcal`. Verificado. Los datos de composición corporal faltan en el 18 % de las filas.

### steps_day y steps_interval

`steps_day`: una fila por día. Origen: `com.samsung.shealth.step_daily_trend`, solo filas con
`source_type` = -2, que es el total del día. Clave: `day`.

| Columna | Tipo | Unidad | Origen | Estado |
|---|---|---|---|---|
| `day` | fecha | | `day_time` | Verificado |
| `steps` | entero | pasos | `count` | Verificado |
| `distance_m` | número | metros | `distance` | Verificado |
| `calorie_kcal` | número | kcal | `calorie` | Verificado |

Las filas con `source_type` 0 y 109 son fuentes parciales y no se importan.
El total coincide con `activity.day_summary.step_count` en los 595 días comparables.

`steps_interval`: una fila por intervalo de 10 minutos, 144 por día. Origen: archivo `binning_data` de
`step_daily_trend`. Clave: `day` + número de intervalo. Columnas `start_at`, `steps`, `distance_m`, `calorie_kcal`.
La suma de los intervalos iguala al total del día en los 595 días. Historia completa desde marzo de 2025. Verificado.

La tabla `tracker.pedometer_step_count`, con pasos minuto a minuto, trae solo 36 días y no se usa.

### activity_day

Una fila por día. Origen: `com.samsung.shealth.activity.day_summary`. Clave: `day`.

| Columna | Tipo | Unidad | Origen | Estado |
|---|---|---|---|---|
| `day` | fecha | | `day_time` | Verificado |
| `steps` | entero | pasos | `step_count` | Verificado |
| `active_min`, `walk_min`, `run_min`, `exercise_min` | número | minutos | `active_time`, `walk_time`, `run_time`, `exercise_time`, que vienen en milisegundos | Verificado |
| `distance_m` | número | metros | `distance` | Verificado |
| `active_calorie_kcal` | número | kcal | `calorie` | Supuesto |
| `floors` | número | pisos | `floor_count` | Verificado |

### vitality_day

Una fila por día. Origen: `com.samsung.shealth.vitality_score`. Clave: `day`.

| Columna | Tipo | Unidad | Origen | Estado |
|---|---|---|---|---|
| `day` | fecha | | `day_time` | Verificado |
| `energy_score` | número | 0 a 100 | `total_score` | Verificado |
| `sleeping_hr` | número | latidos por minuto | `shr_value` | Supuesto |
| `sleeping_hrv_ms` | número | milisegundos | `shrv_value` | Supuesto |

El puntaje de energía es propio de Samsung y su fórmula no es pública. No se usa en los análisis principales.

## 2. Tablas derivadas (se recalculan después de cada importación)

### night

Una fila por noche real: la sesión de sueño de más de 120 minutos de cada `night_date`.
Si una fecha tiene dos sesiones largas se conserva la mayor, y la otra suma en `extra_sleep_min`.

Las señales nocturnas no traen vínculo con el sueño. Se unen por ventana: el registro debe empezar entre
30 minutos antes del inicio del sueño y su final. Si hay varios, se toma el más largo.

| Grupo | Columnas | Origen |
|---|---|---|
| Sueño | `night_date`, `session_id`, `start_at`, `end_at`, `hours`, `fragment_count`, `extra_sleep_min`, `score`, `efficiency_pct`, `physical_recovery`, `mental_recovery`, `movement_awakening`, `bedtime_hour`, `weekday`, `is_weekend_night` | `sleep_session` |
| Etapas | `awake_min`, `light_min`, `deep_min`, `rem_min` | `sleep_stage` |
| Oxígeno | `spo2_avg`, `spo2_min`, `low_minutes`, `intervals_below_90`, `intervals_below_85`, `spo2_recorded_hours` | `spo2_night`, `spo2_interval` |
| Corazón | `hrv_rmssd_ms`, `hrv_sdnn_ms`, `night_hr_avg`, `night_hr_min` | `hrv_window`, `heart_rate_minute` |
| Otras señales | `skin_temp_c`, `skin_temp_vs_baseline_c`, `respiratory_rate_avg` | `skin_temperature`, `respiratory_rate` |
| Ronquido | `snoring_min`, `snoring_events`; vacío si la noche no se grabó | `snoring_event` |
| Contexto del día | `exercise_min`, `exercise_count`, `exercise_types`, `steps`, `stress_avg` | `exercise`, `steps_day`, `stress` |

`weekday` es un número: 1 para lunes y 7 para domingo, según el día en que empezó la noche; la interfaz
lo traduce. `is_weekend_night` es verdadero para viernes y sábado. `bedtime_hour` supera 24 cuando la persona se acuesta
después de medianoche. Las cifras de oxígeno se informan solo para noches con `spo2_recorded_hours` de 3 o más; la tabla guarda
el dato de todas las noches y la capa `queries` aplica la regla.

Otras reglas de cálculo:

- Todas las comparaciones de tiempo se hacen en UTC, para que una noche en otro huso se una bien.
- `hrv_rmssd_ms` y `hrv_sdnn_ms` son la mediana de las ventanas de la noche; `night_hr_avg` y
  `night_hr_min`, el promedio y el mínimo del pulso por minuto entre el inicio y el fin del sueño.
- `intervals_below_90` y `intervals_below_85` cuentan los intervalos de 10 minutos cuyo mínimo quedó bajo
  90 % y bajo 85 %.
- El contexto del día toma el ejercicio, los pasos y el estrés de la fecha `night_date`.
- `exercise_types` lista los tipos del día: el nombre propio si es un tipo creado por el usuario, el
  nombre del código estándar si se conoce, o `type <código>` si no.

Sobre la exportación de septiembre de 2026, `night` da las mismas 503 noches que el prototipo y los
mismos valores en todas las columnas, salvo la variabilidad y el pulso de 8 noches registradas en otro
huso, que el prototipo calculaba con el huso equivocado.

### day

Una fila por cada día del calendario que tiene algún registro diurno.

| Grupo | Columnas | Origen |
|---|---|---|
| Actividad | `day`, `steps`, `active_min`, `distance_m`, `floors`, `active_calorie_kcal` | `steps_day`, `activity_day` |
| Ejercicio grabado | `exercise_min`, `exercise_count`, `exercise_types` | `exercise` |
| Pulso | `hr_avg`, `hr_min`, `hr_max` | `heart_rate_minute`, por hora local |
| Estrés | `stress_avg`, `stress_count` | `stress` |
| Energía | `energy_score` | `vitality_day` |
| Enlaces | `previous_night_date`, `next_night_date` | `night` |

`steps` toma el total de `steps_day` y, si falta, el de `activity_day`. `previous_night_date` es la noche de
la que la persona se despertó ese día; `next_night_date`, la que empezó ese día. Quedan vacíos si no hubo
noche registrada. El diseño pedía también calorías en reposo: la exportación no las separa por día, así
que la columna no existe.

## 3. Tablas propias (la fusión no las toca)

| Tabla | Una fila es | Columnas |
|---|---|---|
| `tag` | Una etiqueta del catálogo | `tag_id`, `name`, `is_active` |
| `annotation` | Una etiqueta puesta sobre una fecha | `day`, `tag_id`, `note`, `created_at`, `updated_at` |
| `user_profile` | Datos personales opcionales para el informe | `name`, `birth_year`, `sex`, `height_cm` |

## 4. Tablas de control

| Tabla | Una fila es | Columnas principales |
|---|---|---|
| `import_log` | Una importación | `import_id`, `imported_at`, `file_name`, `samsung_app_version`, `exported_at`, `first_date`, `last_date` |
| `import_table` | Lo que una importación hizo en una tabla | `import_id`, `table_name`, `new_count`, `updated_count`, `unchanged_count`, `kept_count`, `superseded_count`, `rejected_count` |
| `import_failure` | Un dominio que no se pudo importar | `import_id`, `domain`, `reason` |
| `record_history` | La versión anterior de un registro actualizado | `table_name`, `key`, `replaced_at`, `import_id`, `previous_values` |
| `validation_issue` | Un registro rechazado u observado | `import_id`, `table_name`, `key`, `rule`, `value`, `action` |
| `schema_version` | La versión del esquema de la base | `version`, `applied_at` |
| `sleep_stage_code` | Un código de etapa | `code`, `name`, `is_verified` |
| `exercise_type_code` | Un tipo de ejercicio estándar | `code`, `name`, `is_verified` |

`previous_values` guarda los valores anteriores como texto JSON. Los nombres de los códigos se guardan
en inglés (`light`, `walking`); la interfaz los traduce. Los ejercicios personalizados, como CrossFit,
se resuelven con la tabla `exercise_custom_type`.

### Códigos de etapa de sueño

| Código | Nombre | Estado |
|---|---|---|
| 40001 | Despierto | Supuesto, por descarte |
| 40002 | Ligero | Verificado: sus minutos igualan a `total_light_duration` |
| 40003 | Profundo | Supuesto, por descarte |
| 40004 | REM | Verificado: sus minutos igualan a `total_rem_duration` |

### Códigos de tipo de ejercicio

| Código | Sesiones | Nombre | Estado |
|---|---|---|---|
| 1001 | 191 | Caminata | Supuesto |
| 14001 | 50 | Pesas | Supuesto |
| 0 con `custom_id` `m8yrswqh_1mg` | 17 | CrossFit | Verificado: ejercicio personalizado con ese nombre |
| 0 sin `custom_id` | 15 | Otro | Supuesto |
| 11007 | 11 | Bicicleta | Supuesto |
| 1002 | 6 | Carrera | Supuesto |
| 14003 | 2 | Circuito | Supuesto |
| 10007 | 1 | Sin identificar | Supuesto |

Samsung no incluye en la exportación el diccionario de sus códigos estándar.

## 5. Validaciones de contenido

| Tabla | Regla | Qué pasa si falla |
|---|---|---|
| Todas | Fecha posterior a 2020 y no futura | Registro rechazado |
| `spo2_night`, `spo2_interval` | SpO₂ entre 60 y 100 | Registro rechazado |
| `heart_rate_minute` | Pulso entre 30 y 220 | Registro rechazado |
| `sleep_session` | Duración mayor a 0 y menor a 24 horas | Registro rechazado |
| `sleep_session` | Sin duración | Registro rechazado |
| `skin_temperature`, `skin_temperature_minute` | Temperatura entre 25 y 42 °C | Registro rechazado |
| `respiratory_rate`, `respiratory_rate_minute` | Entre 4 y 40 respiraciones por minuto | Registro rechazado |
| `respiratory_rate`, `respiratory_rate_minute` | Valor 0 | Se guarda vacío; en el resumen de la noche se informa |
| `sleep_stage` | Código fuera del diccionario | Se guarda el código y se informa |
| `spo2_night`, `skin_temperature`, `respiratory_rate` | Registro con el mismo inicio y fin que otro | Queda el primero que creó Samsung; los demás se rechazan |
| Tablas diarias | Dos filas para el mismo día | Vale la última; la otra se informa |
| Series de detalle | Archivo de detalle ausente, vacío o ilegible | El registro madre se guarda y se informa |

Las series por minuto y por intervalo se identifican por `start_utc`, el momento en UTC. La hora local
se repite cuando se viaja hacia el oeste: en la exportación de septiembre de 2026, 111 minutos de
pulso comparten hora local con otro minuto distinto. `start_at` conserva la hora local para mostrar.

Los códigos de ejercicio se guardan tal como vienen; sus nombres se resuelven al consultar.

Samsung a veces escribe, días después, más registros de respiración con el inicio y el fin de una noche ya
registrada y valores distintos: 12 registros en la exportación de noviembre de 2026. No se pueden ubicar
en ninguna noche, así que se conserva el que Samsung creó a la mañana siguiente.

## 6. Tablas de Samsung de ventana corta

Su primer día disponible avanza en cada exportación. Ninguna alimenta la versión 1.

| Tabla de Samsung | Días por exportación |
|---|---|
| `tracker.pedometer_step_count` | 36 |
| `oxygen_saturation.raw` | 35 |
| `sleep_raw_data` | 6 |
| `insight_message` | 188 |

## 7. Pendientes de este diccionario

- Confirmar el significado de `movement_awakening`, `activity_level`, `is_outlier` y de los códigos de electrocardiograma.
- Conseguir los nombres oficiales de los códigos estándar de ejercicio.
