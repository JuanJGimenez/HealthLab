# Registro de decisiones

Cada decisión de diseño con su motivo. Las decisiones 1 a 26 se tomaron durante la planificación,
el 14 de noviembre de 2026. Las siguientes surgieron al construir y se anotan antes de escribirse
en código. Una decisión que reemplaza a otra lo dice en su nota.

| N.º | Decisión | Motivo |
|---|---|---|
| 1 | App local con ventana propia; el dashboard consulta la base en vivo | Un HTML suelto no puede ejecutar el importador ni leer la base |
| 2 | La base vive en `data/` dentro de la carpeta de la app | Un solo lugar conocido; no hay que elegir el archivo |
| 3 | Las importaciones se fusionan, no reemplazan | No perder historia si Samsung recorta datos o cambia el teléfono |
| 4 | En un conflicto gana la exportación más nueva | El día de la exportación llega incompleto y Samsung reprocesa sesiones de sueño |
| 5 | Nunca se borra un registro que falta en la exportación nueva | Protege la historia acumulada |
| 6 | La versión anterior de un registro actualizado se guarda en un historial | La decisión 4 no debe destruir información |
| 7 | Respaldo automático de la base antes de cada fusión | Un error de fusión solo se arregla con una copia anterior |
| 8 | Vista previa y confirmación antes de aplicar una importación | Detectar recálculos o cambios de formato antes de escribir |
| 9 | Se conserva cada zip original importado | Permite reimportar si el importador se corrige después |
| 10 | Contrato por tabla y validaciones de rango | Los cambios de Samsung deben verse, no pasar en silencio |
| 11 | Código, tablas y columnas en inglés; documentación en español | Convención más extendida, con documentación en el idioma del usuario |
| 12 | Proyecto modular por capas, con documentación por función | Poder cambiar la lectura, la base o la pantalla sin tocar el resto |
| 13 | La ventana de la app se abre con pywebview | Toda la lógica es Python; Tauri y Electron la llevarían igual como programa aparte |
| 14 | La interfaz permite elegir entre español e inglés | Requisito del usuario; los textos van en archivos de traducción, fuera del código |
| 15 | La app arranca con una base nueva, sin migrar la del prototipo | Se cargará desde una exportación actualizada de Samsung Health; evita escribir una migración |
| 16 | Se conservan los 2 respaldos más recientes de la base | Alcanza para deshacer una fusión fallida sin acumular copias |
| 17 | Los comentarios y la documentación dentro del código van en inglés | Elección del usuario; coherente con los nombres del código y lista si algún día se publica |
| 18 | Se conservan los 2 zips originales más recientes, y nunca se borra uno con fechas más antiguas que los siguientes | Cada exportación suele traer la historia completa; la excepción protege la historia que Samsung haya recortado |
| 19 | Anotaciones propias: etiquetas de sí o no por fecha, cargadas a mano | Registran lo que el reloj no mide; sin cantidades ni avisos al iniciar, por pedido del usuario |
| 20 | Detalle de una noche con cinco pistas sobre un eje común y comparación de dos noches a elección | Ver qué pasaba en el momento de una caída de oxígeno; las pistas serán configurables más adelante |
| 21 | Vista del día: pantalla hora por hora, perfil del día típico y cruce con la noche siguiente | Relacionar lo que pasa de día con cómo resulta la noche |
| 22 | Los datos de ventana corta se avisan con una leyenda donde se consultan, sin recordatorios | Pedido del usuario; el aviso aparece solo cuando el dato hace falta |
| 23 | Informe para el médico en PDF, armado por bloques a elección, con datos personales opcionales | El usuario quiere sumar todos los datos y gráficos posibles; el resumen de oxígeno va siempre primero |
| 24 | La app se entrega como carpeta portátil con ejecutable, para una sola computadora | No exige instalar Python y mantiene la base dentro de la carpeta; un instalador obligaría a moverla |
| 25 | Construcción en diez etapas, datos primero; Claude escribe el código y el usuario revisa cada etapa | El usuario no escribe código y prioriza buenas prácticas y formato profesional |
| 26 | El detalle de una noche tiene ocho pistas, y el usuario elige cuáles ver desde la primera versión | La etapa 0 mostró que respiración, temperatura y movimiento traen serie por minuto; ayudan a leer una caída de oxígeno |
| 27 | Una capa propia, `pipeline`, conduce la importación de punta a punta | El diseño no decía qué capa coordina el flujo; sin ella, esa lógica terminaría dentro de la interfaz |
| 28 | El proyecto requiere Python 3.12 o superior | Las herramientas de verificación de tipos actuales ya no admiten 3.11; la app empaquetada trae su propio Python |
| 29 | La etapa 2 se divide en 2a, lectura, y 2b, transformación | Regla del plan: una etapa que se alarga se divide; la lectura se puede comprobar sola contra las exportaciones reales |
| 30 | Las tablas se leen como texto; convertir a números y fechas es tarea de la transformación | La capa de lectura no conoce unidades ni significados, y así ningún valor se altera por una conversión automática |

## Notas

- **Decisión 4.** La etapa 0 confirmó el primer motivo. El segundo, el reproceso de sesiones de sueño, no se observó entre las exportaciones de septiembre y noviembre de 2026.
- **Decisión 20.** La cantidad de pistas quedó reemplazada por la decisión 26.
- **Decisión 22.** Tras la etapa 0, ninguna tabla de la primera versión es de ventana corta. El mecanismo queda disponible.
- **Decisiones 27 y 28.** Tomadas en la etapa 1 y aprobadas por el usuario el 15 de noviembre de 2026.
- **Decisiones 29 y 30.** Tomadas en la etapa 2a; pendientes de la confirmación del usuario.
