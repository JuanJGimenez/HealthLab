# Arquitectura

MiSalud es un programa Python que abre una ventana propia y muestra el dashboard adentro. La ventana
habla con Python directamente, sin servidor web ni puertos abiertos (decisiones 1 y 13).

## Capas

El código vive en `src/misalud/` y se organiza en capas. Una capa solo puede importar a las que
están antes en esta lista:

| Orden | Capa | Hace | No hace |
|---|---|---|---|
| 1 | `config` | Rutas, umbrales y rangos de validación | No contiene lógica |
| 2 | `reading` | Abre el zip, lee CSV y JSON, compara con el contrato | No conoce la base |
| 3 | `transform` | Limpia, convierte horas, valida rangos; un módulo por dominio | No escribe en disco |
| 4 | `storage` | Esquema, fusión, respaldos, historial y registro de importaciones | No calcula métricas |
| 5 | `derived` | Reconstruye `night` y `day` desde el detalle | No lee archivos de Samsung |
| 6 | `annotations` | Guarda y lee las etiquetas del usuario | No toca datos de Samsung |
| 7 | `queries` | Responde las preguntas de las pantallas | No modifica datos |
| 8 | `pipeline` | Conduce una importación de punta a punta | No tiene lógica propia de lectura, fusión ni cálculo |
| 9 | `reports` | Arma el informe para el médico | No interpreta ni recomienda |
| 10 | `interface` | Ventana, vistas y botones | No lee archivos ni escribe SQL |

La regla no es una convención: `tests/test_architecture.py` revisa los `import` de cada archivo y
falla si una capa importa a otra que está más arriba.

`pipeline` se agregó en la etapa 1. El diseño describía el flujo de importación, pero no decía qué
capa lo conduce; sin una capa propia, esa coordinación habría terminado dentro de `interface`.

## Módulos de la capa de lectura

| Módulo | Responsabilidad |
|---|---|
| `archive` | Abrir la exportación desde un zip o una carpeta, de forma segura |
| `tables` | Listar las tablas, con sus versiones, y leerlas como texto |
| `details` | Leer los archivos de detalle que nombran las celdas |
| `contracts` | Cargar lo que el importador espera de cada tabla |
| `compatibility` | Comparar una exportación con los contratos y clasificar cada diferencia |
| `errors` | Errores propios de la lectura |

Niveles del informe de compatibilidad:

- **Error:** falta una tabla o una columna clave que MiSalud usa, o una columna numérica pasó a
  texto. Esa tabla no se importa; las demás sí.
- **Advertencia:** otro cambio en una tabla en uso, o una tabla que MiSalud no conoce.
- **Información:** cambios en tablas que MiSalud no usa.

## Flujo de una importación

1. `interface` recibe el zip elegido por el usuario y llama a `pipeline`.
2. `reading` descomprime, lee y compara cada archivo con su contrato.
3. `transform` limpia y valida, un dominio por vez. Si uno falla, los demás continúan.
4. `storage` carga el resultado en una base temporal y lo compara con la real.
5. `interface` muestra la vista previa. Si el usuario confirma, `storage` respalda y fusiona.
6. `derived` recalcula `night` y `day`.
7. `storage` anota la importación y archiva el zip original.

## Dónde viven los datos

Todo lo del usuario está en `data/`, dentro de la carpeta de la app, y queda fuera del control de
versiones:

```
data/
  salud.duckdb    base
  backups/        los 2 respaldos más recientes
  exports/        los zips originales
  logs/           registro técnico
```

`config.app_root()` resuelve la carpeta de la app: la variable `MISALUD_HOME` si está definida, la
carpeta del ejecutable si la app está empaquetada, o la carpeta del proyecto si corre desde el código.

## Documentos relacionados

- `data_dictionary.md`: tablas y columnas de la base.
- `merge_rules.md`: los cuatro casos de la fusión.
- `decisions.md`: registro de decisiones.
