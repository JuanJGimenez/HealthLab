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
| Está en la base y falta en la exportación | Lo conserva | 5 |

## Cómo se decide si un registro "ya existe"

Cada tabla tiene una clave de fusión, definida en el diccionario de datos. Para las tablas que vienen
de un archivo de Samsung es el identificador `datauuid`; para las series por minuto o por intervalo
es la hora de inicio, y para las tablas diarias es el día.

En la etapa 0 se comprobó que los identificadores de la exportación de septiembre de 2026 siguen
intactos en la de noviembre, en todas las tablas de historia completa.

## Qué cambió de verdad entre dos exportaciones reales

Entre septiembre y noviembre de 2026 el tercer caso ocurrió por dos causas:

- **El día de la exportación.** Los pasos del 15 de septiembre habían llegado cortados a la hora en
  que se generó el archivo, y la exportación siguiente trajo el día completo.
- **Recálculo de Samsung.** 48 valores del índice de glicación cambiaron.

Ningún registro ya exportado de sueño, oxígeno, pulso, variabilidad, estrés ni ejercicio cambió.

## Resguardos alrededor de la fusión

1. La importación se carga primero en una base temporal.
2. La app muestra una vista previa: nuevos, actualizados, sin cambios y rechazados, por tabla.
3. Si muchos registros de más de 30 días cambian, la vista previa lo destaca.
4. Solo si el usuario confirma, la app respalda la base y aplica la fusión.
5. Se conservan los 2 respaldos más recientes.

## Costo aceptado

Un registro erróneo que se borra en Samsung Health sigue en MiSalud, porque la fusión nunca borra.

## Cómo se prueba

`tests/support/synthetic_export.py` genera exportaciones falsas con el formato real. Dos
exportaciones con distinta cantidad de días imitan dos exportaciones tomadas en fechas distintas:
la más nueva conserva los identificadores, agrega registros y completa el día que en la anterior
estaba cortado. Las pruebas de la etapa 3 usan ese par para cubrir los cuatro casos.
