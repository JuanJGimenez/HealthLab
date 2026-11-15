# MiSalud

Aplicación de escritorio para Windows que importa las exportaciones de Samsung Health, las acumula
en una base local y permite analizar y relacionar los datos del reloj.

Todos los datos quedan en la computadora. La app no envía nada a ningún servicio.
Muestra tendencias de un reloj de pulsera y no reemplaza una evaluación médica.

## Estado

Versión 0.12.0 (etapas 1 a 9: el plan completo). Importa una exportación con vista previa, fusiona
sin perder datos, muestra seis vistas, el detalle de cada noche con ocho pistas y la comparación de
dos noches, y permite etiquetar fechas y filtrar por etiqueta. Tiene además la pantalla de un día
y el día típico por hora, y genera el informe para el médico en PDF, con bloques opcionales. En
español o en inglés. Se entrega como una carpeta portátil para Windows.

Pendiente: armar la carpeta en Windows y abrir la ventana por primera vez. Hasta acá se armó y
se verificó en Linux. Cuando esa prueba esté hecha, la versión pasa a 1.0.0.

## Usar la app

- Cómo se usa: [`docs/manual.md`](docs/manual.md).
- Cómo se genera `MiSalud.exe`: [`docs/build_windows.md`](docs/build_windows.md). En resumen,
  doble clic en `release\build_windows.bat`.

Para abrirla desde el código, sin empaquetar:

```
pip install ".[ui]"
misalud
```

El plan completo y las decisiones de diseño están en `docs/`.

## Requisitos

Python 3.12 o superior.

## Preparar el entorno de desarrollo

```
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

## Comprobar la calidad

Los cuatro comandos deben terminar sin errores antes de cerrar una etapa:

```
ruff format --check .
ruff check .
mypy
pytest
```

| Herramienta | Qué revisa |
|---|---|
| `ruff format` | Formato uniforme del código |
| `ruff check` | Estilo, errores comunes y documentación de cada función |
| `mypy` | Tipos, en modo estricto |
| `pytest` | Pruebas automáticas, con medición de cobertura |

## Estructura

```
src/misalud/      código, organizado por capas (ver docs/architecture.md)
tests/            pruebas automáticas
tests/support/    exportación sintética con el formato de Samsung Health
release/          armado de la carpeta para Windows (ver docs/build_windows.md)
docs/             manual de uso, arquitectura, diccionario de datos, reglas de fusión y decisiones
data/             base, respaldos y zips originales; fuera del control de versiones
```

## Convenciones

- Código, comentarios y documentación de funciones: en inglés.
- Documentos del proyecto y textos de la interfaz: en español; la interfaz también en inglés.
- Una función sin documentar o sin prueba no se considera terminada.
- Los umbrales que afectan un resultado viven en `config.py`, con su motivo.
