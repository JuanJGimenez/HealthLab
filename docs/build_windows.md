# Generar la carpeta de HealthLab para Windows

Este documento explica cómo convertir el proyecto en la carpeta que se usa: `HealthLab.exe` más sus
piezas. Se hace en la computadora con Windows, una vez por versión.

## Qué hace falta

| Requisito | Detalle |
|---|---|
| Windows 10 u 11, de 64 bits | |
| Python 3.12 o más nuevo | Desde <https://www.python.org/downloads/>. Las pruebas del proyecto corren con Python 3.13. |
| Internet, solo durante el armado | Para descargar las librerías. La app armada no usa internet. |
| Unos 2 GB libres | Para el entorno de armado. La carpeta final pesa alrededor de 200 MB. |

Python hace falta solo para armar. La carpeta resultante funciona sin Python.

## Paso a paso

1. **Instalar Python.** En el instalador, marcar **Add python.exe to PATH**.
2. **Descomprimir el proyecto** en una carpeta de ruta corta y sin sincronización con la nube,
   por ejemplo `C:\proyectos\healthlab`.
3. **Doble clic en `release\build_windows.bat`.** Se abre una ventana negra que:
   1. crea un entorno de Python propio en `.venv-build`;
   2. descarga las librerías;
   3. arma la carpeta con PyInstaller;
   4. ejecuta la autoverificación del programa armado.
4. **Leer el final.** Tiene que decir `RESULT: OK` y `Listo`. La primera vez tarda entre 5 y
   10 minutos.
5. **Copiar `dist\HealthLab`** al lugar donde se va a usar, por ejemplo `C:\HealthLab`.
6. **Abrir `C:\HealthLab\HealthLab.exe`.**

### Los pasos 5 y 6 en uno

Desde una terminal abierta en la carpeta del proyecto:

```
release\build_windows.bat --install C:\HealthLab
```

Arma, verifica y deja el programa en `C:\HealthLab`. Sirve igual para la primera instalación y para
cada actualización: reemplaza `HealthLab.exe`, `_internal`, `Manual.md`, `LICENSE.txt` y
`THIRD_PARTY_LICENSES.txt`, y no toca `data`.

### Probar una importación completa antes de usarla

```
release\build_windows.bat --sample C:\ruta\a\samsunghealth.zip
```

El programa armado importa ese archivo en una carpeta temporal y la descarta. La autoverificación
agrega una línea `import` con la cantidad de noches y de días.

## Actualizar a una versión nueva

1. Cerrar HealthLab.
2. Descomprimir el proyecto nuevo, reemplazando el anterior.
3. Ejecutar `release\build_windows.bat --install C:\HealthLab`.

A mano, sin `--install`: borrar `HealthLab.exe` y `_internal` de la carpeta en uso y copiar los
nuevos desde `dist\HealthLab`. **Nunca borrar ni reemplazar `data`.**

### Desde una carpeta de MiSalud

Hasta la versión 1.0.1 la app se llamaba MiSalud. Para actualizar, usar `--install` con la carpeta
de siempre, por ejemplo `release\build_windows.bat --install C:\MiSalud`: instala `HealthLab.exe`,
quita `MiSalud.exe` y deja `data` intacta. La base conserva su nombre, `salud.duckdb`, así que los
datos se abren sin cambios.

## Qué revisa la autoverificación

| Línea | Qué prueba |
|---|---|
| `page files` | Están los archivos de la pantalla, con la librería de gráficos. |
| `texts` | Se leen los textos en español y en inglés, de la app y del informe. |
| `table contracts` | Se lee la descripción de las tablas de Samsung. |
| `window library` | Está la librería que abre la ventana. |
| `data folder` | La carpeta de datos se puede crear y escribir. |
| `database` | La base se crea o se actualiza, con sus tablas calculadas. |
| `report` | Se genera un informe en PDF. |
| `import` | Solo con `--sample`: una importación de punta a punta. |

La autoverificación no abre la ventana. Que la ventana se vea bien se comprueba abriendo el
programa.

## Problemas frecuentes

| Qué pasa | Motivo y salida |
|---|---|
| "No se encontró Python 3.12 o más nuevo" | Instalar Python y marcar la opción del PATH; después cerrar y volver a abrir la ventana. |
| Falla al instalar las librerías | Sin internet, o un Python demasiado nuevo para alguna librería. Probar con Python 3.13. |
| El antivirus borra `HealthLab.exe` | Los programas armados con PyInstaller y sin firma dan falsas alarmas. Agregar la carpeta como excepción. |
| "Windows protegió su PC" al abrir | Más información, Ejecutar de todas formas. |
| `ERROR: ... PermissionError` al usar `--install` | HealthLab está abierto. Cerrarlo y repetir. |
| La ventana abre en blanco | Falta WebView2 de Microsoft; viene con Windows 11 y con Edge. |

## Archivos de esta parte del proyecto

| Archivo | Para qué |
|---|---|
| `release/build_windows.bat` | Prepara el entorno y llama al armado. Es lo único que hace falta ejecutar. |
| `release/build.py` | Arma, verifica e instala. |
| `release/notices.py` | Junta las licencias de las librerías que van en la carpeta, para `THIRD_PARTY_LICENSES.txt`. |
| `release/healthlab.spec` | La receta de PyInstaller: qué entra en la carpeta. |
| `release/launcher.py` | El punto de entrada del programa. |
| `release/healthlab.ico` | El ícono. `release/make_icon.py` lo vuelve a dibujar. |

## Estado de la comprobación

El procedimiento se ejecutó en Windows el 18 de noviembre de 2026: el armado terminó con
`RESULT: OK`, la ventana abrió, importó una exportación y mostró las vistas, sin avisos de Windows
ni del antivirus. Antes se había armado y verificado en Linux, con una importación completa de una
exportación real.
