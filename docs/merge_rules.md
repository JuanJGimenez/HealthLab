# Reglas de fusión

Una importación nunca reemplaza la base: la fusiona con lo que ya hay (decisión 3).
La fusión trabaja sobre las tablas de detalle. Las tablas derivadas se recalculan después,
y las tablas propias del usuario no se tocan.

## Los cuatro casos

| Caso | Qué hace la fusión | Decisión |
|---|---|---|
| El registro no existe en la base | Lo agrega | 3 |
| Existe y es idéntico | No lo toca | 3 |
| Existe con valores distintos | Guarda la versión anterior en `record_history` y escribe la nueva | 4 y 6 |
| Existe con valores distintos, pero la base ya tiene una exportación más reciente | Conserva lo guardado y lo cuenta como "superado" | 34 |
| Está en la base y falta en la exportación | Lo conserva | 5 |

## Cómo se decide si un registro "ya existe"

Cada tabla tiene una clave de fusión, definida en el diccionario de datos. Para las tablas que vienen
de un archivo de Samsung es el identificador `datauuid`; para las series por minuto o por intervalo
es el momento de inicio en UTC, junto con la noche a la que pertenecen cuando corresponde, y para
las tablas diarias es el día. `storage/schema.py` define la clave de cada tabla.

En la etapa 0 se comprobó que los identificadores de la exportación de septiembre de 2026 siguen
intactos en la de noviembre, en todas las tablas de historia completa.

## Qué cambió de verdad entre dos exportaciones reales

En la etapa 0 se vieron dos cambios entre septiembre y noviembre de 2026, ambos en tablas que
HealthLab no importa:

- **El día de la exportación.** Del 15 de septiembre faltaban las filas de pasos por fuente (reloj
  y teléfono), que aparecieron en la exportación siguiente. La fila con el total del día, la única
  que se importa, ya estaba completa.
- **Recálculo de Samsung.** 48 valores del índice de glicación cambiaron.

La etapa 3 fusionó las dos exportaciones reales: de los 2.550.780 registros de septiembre, ninguno
cambió en noviembre. El tercer caso existe como resguardo; hasta ahora no ocurrió con datos reales.

## Resguardos alrededor de la fusión

1. La importación se carga primero en tablas temporales, en memoria, que nunca tocan las tablas reales.
2. La app muestra una vista previa: nuevos, actualizados, sin cambios y rechazados, por tabla.
3. Si muchos registros de más de 30 días cambian, la vista previa lo destaca.
4. Solo si el usuario confirma, la app respalda la base y aplica la fusión. La primera importación
   no genera respaldo, porque no hay nada que proteger.
5. La fusión completa ocurre en una sola transacción: si algo falla, la base queda como estaba.
6. Se conservan los 2 respaldos más recientes.

## Importar una exportación vieja después de una nueva

Si la base ya tiene una exportación más reciente, la vieja solo agrega los registros que falten.
Los que difieren quedan como están y la vista previa los cuenta como "superados".

## Costo aceptado

Un registro erróneo que se borra en Samsung Health sigue en HealthLab, porque la fusión nunca borra.

## Cómo se prueba

`tests/support/synthetic_export.py` genera exportaciones falsas con el formato real. Dos
exportaciones con distinta cantidad de días imitan dos exportaciones tomadas en fechas distintas:
la más nueva conserva los identificadores, agrega registros y completa el día que en la anterior
estaba cortado. Las pruebas de `tests/test_storage_merge.py` usan ese par y tablas mínimas para
cubrir los cuatro casos, la exportación vieja y el fallo a mitad de la fusión.
