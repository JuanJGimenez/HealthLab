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
| 31 | Las series por minuto y por intervalo se identifican por el momento en UTC, y guardan además la hora local | La hora local se repite al viajar hacia el oeste; identificar por ella borraba 111 minutos de pulso reales |
| 32 | Cada dominio se transforma por separado; si uno falla, los demás siguen | Aplica la decisión 10: un cambio de Samsung en una tabla no debe impedir importar el resto |
| 33 | Un valor 0 de frecuencia respiratoria se guarda vacío y el registro se conserva | En esa tabla 0 significa sin medición; rechazar la noche entera perdía sus otros datos |
| 34 | Una exportación más vieja que la última importada agrega lo que falta, pero no pisa nada | "La exportación más nueva gana" debe valer también si los archivos se importan en desorden |
| 35 | La vista previa se arma en tablas temporales en memoria, no en una segunda base en disco | Mismo resguardo, sin archivos intermedios que limpiar; las tablas reales no se tocan hasta confirmar |
| 36 | La primera importación no genera respaldo | Una base vacía no tiene nada que proteger y ocuparía uno de los dos lugares |
| 37 | `night` y `day` se calculan dentro de la base, y las señales se unen a la noche comparando en UTC | Recalcular todo tarda menos de un segundo, y una noche registrada en otro huso queda bien unida |
| 38 | Un registro nocturno que repite el inicio y el fin de otro se rechaza; queda el primero que creó Samsung | Samsung reescribe días después registros de respiración sobre una noche ya registrada; no hay cómo ubicarlos |
| 39 | Los días de la semana se guardan como número y los nombres de códigos en inglés; la interfaz traduce | La interfaz es bilingüe (decisión 14); la base no debe depender del idioma |
| 40 | La tabla `day` no tiene calorías en reposo | La exportación no las separa por día; el diseño las pedía |
| 41 | Todas las cifras se calculan en Python; la página solo dibuja | El prototipo calculaba en la página; así cada número tiene una prueba automática y una sola definición |
| 42 | La librería de gráficos (Apache ECharts 5.6) viaja dentro de la app | La app no se conecta a internet; la licencia Apache 2.0 lo permite y va incluida |
| 43 | La página se prueba en un navegador real, conectada a Python sin la ventana | Permite probar de punta a punta, de la app vacía al dashboard, en cada cambio |
| 44 | Las tablas calculadas llevan su propio número de versión y se recalculan solas si cambia | Una actualización de la app puede cambiar una columna de `night` sin que el usuario tenga que reimportar |
| 45 | La etapa 6 se divide en 6a (detalle de una noche y carga de etiquetas) y 6b (comparar dos noches y usar las etiquetas en las vistas) | Regla del plan: una etapa que se alarga se divide; la 6a ya se puede usar sola |
| 46 | El tiempo bajo 85 % de oxígeno se mide en minutos, no en cantidad de intervalos | El reloj informa cada minuto en unas noches y cada 10 en otras; contar intervalos mezclaba las dos |
| 47 | Las etiquetas iniciales se agregan con la primera migración de esquema (versión 2) | Desde la versión 0.6.0 el usuario pudo haber creado una base; todo cambio va por migración |
| 48 | La nota libre de una fecha se guarda bajo una etiqueta reservada | Mantiene una sola tabla, `annotation`, como pedía el diseño |
| 49 | Desactivar una etiqueta no borra sus marcas; una etiqueta inicial renombrada deja de traducirse | Nada de lo que cargó el usuario se pierde, y su nombre vale más que la traducción |
| 50 | El filtro por etiqueta se aplica a las vistas de noches, no a la vista Actividad | Actividad agrupa días, y la regla de etiquetas por día llega con la vista del día (etapa 7) |
| 51 | La comparación con y sin etiqueta vive en la vista Relacionar | Es la vista donde se buscan relaciones; evita sumar una séptima pestaña |

## Notas

- **Decisión 4.** La etapa 3 fusionó las exportaciones de septiembre y noviembre de 2026 y ningún registro importado cambió. Los cambios vistos en la etapa 0 estaban en tablas que MiSalud no importa. La regla queda como resguardo.
- **Decisión 20.** La cantidad de pistas quedó reemplazada por la decisión 26.
- **Decisión 22.** Tras la etapa 0, ninguna tabla de la primera versión es de ventana corta. El mecanismo queda disponible.
- **Decisiones 27 y 28.** Tomadas en la etapa 1 y aprobadas por el usuario el 15 de noviembre de 2026.
- **Decisiones 29 y 30.** Tomadas en la etapa 2a y aprobadas por el usuario el 15 de noviembre de 2026.
- **Decisiones 31 a 33.** Tomadas en la etapa 2b y aprobadas por el usuario el 15 de noviembre de 2026.
- **Decisiones 34 a 36.** Tomadas en la etapa 3 y aprobadas por el usuario el 15 de noviembre de 2026.
- **Decisiones 37 a 40.** Tomadas en la etapa 4 y aprobadas por el usuario el 15 de noviembre de 2026.
- **Decisiones 41 a 44.** Tomadas en la etapa 5 y aprobadas por el usuario el 15 de noviembre de 2026.
- **Decisiones 45 a 48.** Tomadas en la etapa 6a y aprobadas por el usuario el 15 de noviembre de 2026.
- **Decisiones 49 a 51.** Tomadas en la etapa 6b; pendientes de la confirmación del usuario.
- **Esquema.** La etapa 4 agregó la tabla `exercise_custom_type` a la versión 1 del esquema, sin migración, porque todavía no existe ninguna base en uso. Desde la primera entrega que el usuario instale, todo cambio de esquema irá por migración.
