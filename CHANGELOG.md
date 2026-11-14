# Registro de cambios

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa
[versionado semántico](https://semver.org/lang/es/).

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
