# Manual de uso de MiSalud

MiSalud guarda en tu computadora los datos que exporta Samsung Health y te deja mirarlos,
relacionarlos y llevarlos a una consulta médica.

Tres cosas para tener presentes:

- **Todo queda en tu computadora.** La app no se conecta a internet ni envía nada.
- **Nada se pierde.** Cada exportación nueva se suma a lo que ya estaba guardado.
- **Un reloj de pulsera no reemplaza un estudio médico.** La app muestra tendencias para conversar
  con un profesional; no diagnostica.

## 1. La carpeta de la app

| Elemento | Qué es | Qué hacer con él |
|---|---|---|
| `MiSalud.exe` | El programa. | Doble clic para abrir. |
| `_internal` | Piezas que el programa necesita. | No tocar. |
| `Manual.md` | Este manual. | Se abre con el Bloc de notas. |
| `data` | Tus datos: la base, los respaldos y las exportaciones originales. Aparece la primera vez que abrís la app. | Cuidarla: es lo único irreemplazable. |

La carpeta puede estar en cualquier lugar donde puedas escribir, por ejemplo `C:\MiSalud`. No la
pongas dentro de `C:\Archivos de programa` ni en una carpeta sincronizada con la nube (OneDrive,
Google Drive): la sincronización saca tus datos de salud de la computadora y puede dañar la base
si actúa mientras la app está abierta.

**Respaldo completo:** con la app cerrada, copiá la carpeta `data` (o la carpeta entera) a un disco
externo.

### La primera vez que abrís el programa

Windows puede mostrar el aviso "Windows protegió su PC", porque el programa no está firmado por
una empresa. Elegí **Más información** y después **Ejecutar de todas formas**. Pasa una sola vez.

## 2. Sacar los datos de Samsung Health

1. En el teléfono, abrí **Samsung Health**.
2. Entrá al menú de tres puntos y después a **Ajustes**.
3. Buscá **Descargar datos personales** y confirmá. Puede tardar unos minutos.
4. El teléfono deja una carpeta llamada `samsunghealth_…` dentro de `Download/Samsung Health`.
5. Pasá esa carpeta a la computadora, por cable o como prefieras.
6. Si no es ya un archivo `.zip`, hacé clic derecho sobre la carpeta y elegí
   **Comprimir en archivo ZIP**.

Los nombres de los menús pueden cambiar con las versiones de Samsung Health.

Cada exportación trae todo el historial, así que no hace falta exportar seguido. Una vez por mes
alcanza.

## 3. Importar

1. Abrí MiSalud y elegí **Actualizar datos** (la primera vez, **Elegir el archivo de Samsung
   Health**).
2. Elegí el archivo `.zip`.
3. Esperá la **vista previa**: tarda alrededor de medio minuto. Todavía no se guardó nada.
4. Leé la vista previa y elegí **Confirmar e importar**, o **Cancelar**.

### Cómo leer la vista previa

| Columna | Significado |
|---|---|
| Nuevos | Registros que no estaban en tu base. Se agregan. |
| Actualizados | Registros que Samsung cambió. Se guarda el valor nuevo y el anterior queda en el historial. |
| Sin cambios | Ya estaban, iguales. |
| Conservados | Están en tu base y no vinieron en esta exportación. Se quedan. |
| Rechazados | Registros con un error evidente, por ejemplo una fecha imposible. No se guardan y quedan anotados. |

Avisos que pueden aparecer:

- **Exportación más vieja que la última importada.** Solo se agregan los registros que falten.
- **Registros de más de 30 días que cambiaron.** Es poco habitual; conviene mirar antes de
  confirmar.
- **El formato de Samsung cambió.** Alguna tabla no se puede leer. El resto se importa igual; para
  recuperar esa tabla hace falta una versión nueva de la app.

Antes de cada fusión la app guarda un respaldo de la base, y conserva los dos últimos.

## 4. Los filtros

Arriba de las vistas hay tres filtros que valen para todas:

- **Período:** 90 días, 6 meses, 12 meses o todo. Se cuenta hacia atrás desde la última noche
  registrada.
- **Noches:** todas, viernes y sábado, o domingo a jueves, según el día en que te acostás.
- **Etiqueta:** todas las noches, solo las que tienen una etiqueta, o solo las que no la tienen.

## 5. Las vistas

### Oxígeno

- **Minutos bajo 90 %, noche a noche.** El tiempo que pasaste con oxígeno bajo mientras dormías.
  La línea marca 5 minutos.
- **SpO₂ mínimo de cada noche.** El valor más bajo. Un punto aislado puede ser un error del
  sensor; pesa más cuando coincide con muchos minutos bajo 90 %.
- **Por día de la semana.** Qué días se repiten las noches con 5 minutos o más.
- **Las noches más complicadas.** Una tabla que se puede ordenar.
- **Calendario.** Un cuadro por noche. Un clic en un día permite anotarlo.

Las cifras de oxígeno usan solo noches con al menos 3 horas de registro.

### Sueño, Corazón y Actividad

Horas dormidas, eficiencia y etapas; pulso y variabilidad durante el sueño; pasos, minutos activos
y el día típico hora por hora.

### Relacionar

Elegís dos medidas y cada noche es un punto. La app informa la correlación y cuántas noches
entraron. Las medidas que empiezan con "Día" son del día en que empezó la noche: sirven para ver,
por ejemplo, si los días con más pasos terminan en noches distintas.

Acá también se comparan las noches con y sin una etiqueta.

Una correlación no prueba que una cosa cause la otra.

### Datos

La tabla noche por noche. **Descargar CSV** la guarda en un archivo que abre Excel.

## 6. El detalle de una noche

Un clic en una noche, en cualquier gráfico o tabla, abre su detalle.

- **Pistas.** Hasta ocho señales sobre el mismo eje de tiempo: etapas del sueño, oxígeno, pulso,
  variabilidad, ronquido, respiración, temperatura de piel y movimiento. Elegís cuáles ver.
- **Franjas naranjas.** Los intervalos con oxígeno bajo 90 %.
- **Zoom.** Con la rueda del mouse.
- **Comparar con otra noche.** Muestra dos noches una debajo de la otra, alineadas por la hora del
  reloj o por las horas desde que te dormiste.

## 7. Etiquetas y notas

Una etiqueta responde sí o no para una fecha: alcohol, cena tarde, congestión nasal, siesta,
enfermedad, viaje, medicación, entrenamiento intenso. Vale para el día y para la noche que empieza
esa tarde.

- Se cargan desde el detalle de una noche o desde el calendario.
- Cada fecha admite además una nota libre.
- En **Etiquetas** podés crear las tuyas, cambiarles el nombre o desactivarlas. Desactivar una
  etiqueta no borra lo que ya marcaste.

La app nunca pide que anotes: cargás lo que quieras, cuando quieras.

## 8. La pantalla de un día

Desde una fecha, **Ver el día** muestra de 0 a 24 horas el pulso, el estrés, los pasos, el
ejercicio grabado y el sueño.

## 9. El informe para el médico

**Informe** genera un PDF en tamaño A4.

1. Elegí el período.
2. Si querés, escribí el modelo del reloj e incluí tus datos personales en el encabezado.
3. Marcá los bloques opcionales: Corazón, Sueño, Ronquido, Actividad, Día y noche, Anotaciones.
4. Si querés, elegí hasta dos noches para mostrar en detalle.
5. **Generar PDF** y elegí dónde guardarlo.

El informe siempre abre con el resumen de oxígeno nocturno, y cierra con el método y las
limitaciones de los datos.

El PDF contiene datos de salud. La app no lo envía a ningún lado; compartirlo es tu decisión.

## 10. El panel "Base de datos"

Muestra la última importación, hasta qué fecha hay datos, el tamaño de la base y la **versión de
MiSalud**. También:

- **Abrir la carpeta** de datos.
- **Historial de importaciones.**
- **Validaciones:** qué registros se rechazaron o se guardaron con una observación.
- **Respaldos:** los dos últimos, con el botón **Restaurar**. Restaurar reemplaza la base actual
  por ese respaldo.

## 11. Idioma y tema

La app se usa en español o en inglés, con tema claro u oscuro. La elección queda guardada.

## 12. Actualizar la app

Una versión nueva reemplaza `MiSalud.exe`, `_internal` y `Manual.md`. La carpeta `data` no se
toca. Si la base necesita un cambio, la app lo hace sola al abrirse.

El paso a paso está en `docs/build_windows.md`, dentro del proyecto.

## 13. Si algo falla

| Qué pasa | Qué hacer |
|---|---|
| La app no abre y muestra un mensaje | El detalle queda en `data\logs\error.log`. |
| La app no abre y no muestra nada | Abrí una terminal en la carpeta y ejecutá `MiSalud.exe --check`. El resultado queda en `data\logs\check.txt`. |
| La ventana abre en blanco | Falta el componente WebView2 de Microsoft. Viene con Windows 11 y con Edge; se puede instalar desde el sitio de Microsoft. |
| Una importación salió mal | Panel "Base de datos", **Restaurar** el respaldo anterior. Las exportaciones originales están en `data\exports`. |
| Windows o el antivirus bloquean el programa | Ver "La primera vez que abrís el programa". |

`MiSalud.exe --check` revisa que la app esté completa sin abrir la ventana. Con un archivo después,
`MiSalud.exe --check exportacion.zip`, prueba además una importación entera en una carpeta
temporal, sin tocar tus datos.
