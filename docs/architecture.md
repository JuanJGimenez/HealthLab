# Arquitectura

HealthLab es un programa Python que abre una ventana propia y muestra el dashboard adentro. La ventana
habla con Python directamente, sin servidor web ni puertos abiertos (decisiones 1 y 13).

## Capas

El código vive en `src/healthlab/` y se organiza en capas. Una capa solo puede importar a las que
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

- **Error:** falta una tabla o una columna clave que HealthLab usa, o una columna numérica pasó a
  texto. Esa tabla no se importa; las demás sí.
- **Advertencia:** otro cambio en una tabla en uso, o una tabla que HealthLab no conoce.
- **Información:** cambios en tablas que HealthLab no usa.

## Módulos de la capa de base de datos

| Módulo | Responsabilidad |
|---|---|
| `schema` | Describir cada tabla: columnas, tipos y clave de fusión |
| `database` | Abrir la base, crear el esquema y aplicar las migraciones pendientes |
| `merge` | Vista previa y fusión con las cuatro reglas, en una transacción; registro de la importación |
| `backup` | Respaldar la base, conservar los 2 respaldos más recientes y restaurar uno |
| `exports` | Guardar los zips originales y borrar los que ya no hacen falta |
| `errors` | Errores propios de la base |

La base guarda su número de versión de esquema. Al abrirla, HealthLab aplica las migraciones que le
falten, todas juntas o ninguna, y se niega a abrir una base creada por una versión más nueva.

`pipeline.importing` conduce una importación en dos pasos: `prepare_import` lee, transforma y arma
la vista previa sin guardar ningún registro; `confirm_import` respalda, fusiona, recalcula las
tablas `night` y `day` y archiva el zip.

## Módulos de cálculo y de consulta

| Capa | Módulo | Responsabilidad |
|---|---|---|
| `derived` | `night` | Una fila por noche real, con cada señal unida por ventana de tiempo |
| `derived` | `day` | Una fila por día, enlazada con la noche anterior y la siguiente |
| `derived` | `rebuild` | Recalcular las dos tablas completas, en una transacción |
| `queries` | `common` | Filtro de período y resultados como datos simples |
| `queries` | `nights` | Lista de noches, resumen de oxígeno, peores noches, promedios por mes y por día de la semana, relación entre dos métricas |
| `queries` | `days` | Lista de días y promedios por mes |
| `queries` | `database` | Historial de importaciones, tamaño de cada tabla y período disponible |
| `queries` | `night_detail` | Una noche con sus ocho pistas; cada pista es una consulta independiente registrada en una lista |
| `queries` | `day_detail` | Un día con sus cinco pistas, de 0 a 24 horas, y el día típico por hora |
| `queries` | `coverage` | Avisos cuando el período consultado no está cubierto por una tabla de ventana corta |
| `annotations` | `store` | Etiquetas y nota libre de cada fecha, y administración del catálogo de etiquetas; la fusión nunca escribe aquí |

Las consultas devuelven listas y diccionarios con texto, números y vacíos, listos para pasar a la
ventana. Una pantalla solo puede pedir métricas de una lista fija, porque el nombre de la métrica
termina dentro de la consulta.

## Módulos del informe

| Módulo | Responsabilidad |
|---|---|
| `queries.report` | Cifras que solo usa el informe: resumen, serie noche a noche, 10 noches destacadas y patrones por etiqueta |
| `annotations.profile` | Datos personales para el encabezado, guardados solo en la base |
| `reports.content` | Reunir todas las cifras como datos simples, para probarlas sin leer un PDF |
| `reports.texts` y `locales/` | Textos del informe y formato de números y fechas, por idioma |
| `reports.charts` | Los dos gráficos del bloque base, dibujados como formas vectoriales |
| `reports.plots` | Los gráficos de los bloques opcionales: líneas, barras apiladas, puntos y las pistas de una noche |
| `reports.pdf` | Armar las páginas A4 y guardar el PDF |

El informe presenta datos y no interpreta: no trae diagnósticos ni recomendaciones. La primera
página es siempre el resumen. Cada bloque opcional es una función registrada en una lista, igual
que las pistas: sumar un bloque no obliga a tocar los demás.

## Módulos de la interfaz

| Módulo | Responsabilidad |
|---|---|
| `api` | Lo único que la página puede pedirle a Python: datos de cada vista, importación en dos pasos, panel de la base, idioma y tema |
| `answers` | La forma declarada de la respuesta de cada método de `api` |
| `i18n` y `locales/` | Los textos, un archivo por idioma (`es.json`, `en.json`) |
| `settings` | Recordar el idioma y el tema en `data/settings.json` |
| `window` | Abrir la ventana con pywebview y mostrar los selectores de archivo |
| `startup` | Decidir qué hace un arranque: abrir la ventana o autoverificarse; si la ventana no abre, dejar el error en `data/logs/error.log` |
| `selfcheck` | Revisar que una copia de la app esté completa, sin abrir la ventana |
| `web/` | La página: `index.html`, `app.css`, `app.js` y la librería de gráficos en `vendor/` |

Reglas de la interfaz:

- La página no calcula ni lee archivos: llama a un método de `api` y dibuja lo que recibe.
- Cada método devuelve datos simples y, si algo falla, un mensaje de error en lugar de cortar la app.
- Ninguna frase está escrita en la página: todas salen de los archivos de idioma. Una prueba
  revisa que los dos idiomas tengan los mismos textos y que la página no pida ninguno que falte.
- La ventana no abre puertos ni se conecta a internet.

### El acuerdo entre Python y la página

La página es JavaScript y lee cada respuesta por el nombre de sus campos. Para que un campo
renombrado o faltante no aparezca recién en la pantalla, el acuerdo tiene una forma escrita y
tres controles:

| Control | Qué compara | Cuándo corre |
|---|---|---|
| Control de tipos (`mypy`) | El código de `api` y de las consultas con las formas declaradas en `answers` | En cada control de calidad |
| `tests/support/contract.py` | Cada respuesta real con su forma declarada, a cualquier profundidad | En todas las pruebas de la interfaz |
| Lecturas faltantes | Cada campo que la página lee con lo que Python envió | En la prueba de punta a punta |

Las filas que salen directo de una consulta (una noche, un mes, una importación) se declaran como
registros simples: sus columnas están en `data_dictionary.md` y el tercer control cubre las que la
página usa.

Cómo se prueba: `tests/test_interface_api.py` cubre cada método de `api`, y
`tests/test_interface_page.py` abre la página en un navegador real (Playwright) y recorre el camino
completo: app vacía, importar, vista previa, confirmar, las seis vistas, los filtros, el panel de la
base y el cambio de idioma. El módulo `window` no tiene prueba automática: necesita una ventana real
y se comprueba a mano en Windows.

## Flujo de una importación

1. `interface` recibe el zip elegido por el usuario y llama a `pipeline`.
2. `reading` descomprime, lee y compara cada archivo con su contrato.
3. `transform` limpia y valida, un dominio por vez. Si uno falla, los demás continúan.
4. `storage` carga el resultado en tablas temporales y lo compara con la base.
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

`config.app_root()` resuelve la carpeta de la app: la variable `HEALTHLAB_HOME` si está definida, la
carpeta del ejecutable si la app está empaquetada, o la carpeta del proyecto si corre desde el código.

## Empaquetado

La carpeta `release/` convierte el proyecto en la carpeta portátil para Windows. No es una capa de
la app: nada de `src/` la importa.

| Archivo | Responsabilidad |
|---|---|
| `build_windows.bat` | Crear el entorno de armado y llamar a `build.py` |
| `build.py` | Armar con PyInstaller, ejecutar la autoverificación del resultado e instalar sobre una carpeta en uso sin tocar `data` |
| `healthlab.spec` | Receta de PyInstaller: el código sale de `src/` y los archivos de la app se listan uno por uno |
| `notices.py` | Seguir los requisitos de la app en el entorno de armado y escribir `THIRD_PARTY_LICENSES.txt` con la licencia de cada librería que viaja en la carpeta |
| `launcher.py` | Punto de entrada del ejecutable |

El armado falla si el programa armado no pasa su autoverificación. `tests/test_release_build.py`
prueba la instalación sobre una carpeta con datos, también una de antes del cambio de nombre, y
`tests/test_release_notices.py` prueba la lista de licencias. El procedimiento completo está en
`build_windows.md`.

## Documentos relacionados

- `data_dictionary.md`: tablas y columnas de la base.
- `merge_rules.md`: los cuatro casos de la fusión.
- `decisions.md`: registro de decisiones.
- `manual.md`: manual de uso.
- `build_windows.md`: cómo generar la carpeta para Windows.
