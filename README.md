# MiSalud

Aplicación de escritorio para Windows que importa las exportaciones de Samsung Health, las acumula
en una base local y permite analizar y relacionar los datos del reloj.

Todos los datos quedan en la computadora. La app no envía nada a ningún servicio.
Muestra tendencias de un reloj de pulsera y no reemplaza una evaluación médica.

## Estado

Versión 0.2.0: esqueleto y capa de lectura (etapas 1 y 2a). Abre y lee una exportación completa y
compara su estructura con los contratos. Todavía no guarda datos ni abre ventana.
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
docs/             arquitectura, diccionario de datos, reglas de fusión y decisiones
data/             base, respaldos y zips originales; fuera del control de versiones
```

## Convenciones

- Código, comentarios y documentación de funciones: en inglés.
- Documentos del proyecto y textos de la interfaz: en español; la interfaz también en inglés.
- Una función sin documentar o sin prueba no se considera terminada.
- Los umbrales que afectan un resultado viven en `config.py`, con su motivo.
