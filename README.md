# IA en un ESP32: primeros pasos con TinyML

Cómo preparar un ESP32 clásico (ESP32-D0WD-V3) en Windows para ejecutar modelos de IA con
**TensorFlow Lite Micro**, usando **ESP-IDF** y **VS Code**. Recoge la instalación, la secuencia de
trabajo, las pruebas realizadas (`blink` y `hello_world`), los problemas encontrados y lo que se
puede hacer a continuación.

## Índice

1. [Resumen](#1-resumen)
2. [Requisitos](#2-requisitos)
3. [Instalación](#3-instalación)
4. [Flujo de trabajo](#4-flujo-de-trabajo)
5. [Pruebas realizadas](#5-pruebas-realizadas)
6. [Referencia rápida](#6-referencia-rápida)
7. [Qué se puede ejecutar en un ESP32](#7-qué-se-puede-ejecutar-en-un-esp32)
8. [Próximos pasos](#8-próximos-pasos)

---

## 1. Resumen

| Prueba | Estado | Resultado |
|---|---|---|
| Instalar ESP-IDF v5.5.5 en Windows | Hecho | Requirió corregir un conflicto con el Python de MSYS2 |
| `blink` (LED) | Hecho | LED del GPIO 2 parpadeando cada 500 ms |
| `hello_world` de TFLite Micro | Hecho | Red neuronal INT8 aproximando `sin(x)`, error medio 0.037 |
| Medir tiempo de inferencia y memoria | Pendiente | [Ver cómo](#81-medir-el-rendimiento-del-hello_world) |
| Modelo propio entrenado en el PC | Pendiente | [Propuesta](#82-un-modelo-propio-dígitos-8x8) |

## 2. Requisitos

**Hardware**

| Elemento | Detalle |
|---|---|
| Chip | ESP32-D0WD-V3 (rev. v3.1), Xtensa dual core, WiFi y Bluetooth |
| Memoria | ~520 KB de SRAM, sin PSRAM. Flash de 4 MB |
| Periféricos | Sin cámara ni micrófono |
| Conexión | USB, puerto serie `COM3` |

**Software**

| Elemento | Versión |
|---|---|
| Sistema operativo | Windows |
| Editor | VS Code con la extensión **ESP-IDF 2.2.0** (Espressif Systems) |
| Framework | **ESP-IDF v5.5.5**, instalado en `C:\esp` con el Installation Manager (EIM) |
| Herramientas | `C:\Espressif\tools` (incluye el entorno virtual de Python de ESP-IDF) |
| Python del sistema | 3.11.8 (oficial, de python.org) |
| esptool | 4.12.0 |

**Qué limita un ESP32 clásico.** El ESP32-S3 añade instrucciones vectoriales (SIMD) que aceleran las
convoluciones, y muchas placas S3 traen PSRAM. El ESP32 clásico no tiene ninguna de las dos cosas, así
que solo caben modelos muy pequeños:

- Adecuado: clasificación de datos de sensores, gestos, palabras clave, imágenes muy pequeñas.
- No adecuado: los LLM de la [sección 7](#7-qué-se-puede-ejecutar-en-un-esp32) o la detección de
  objetos tipo YOLO.

## 3. Instalación

### 3.1 Antes de empezar: comprobar Python

El instalador de ESP-IDF busca un ejecutable llamado `python3.exe`. El Python de python.org solo
instala `python.exe`, por lo que el instalador puede acabar usando otro Python que haya en el PATH,
como el de MSYS2, que ESP-IDF no soporta. Comprobarlo antes de instalar:

```powershell
where.exe python3
```

(En PowerShell hay que escribir `where.exe`; `where` es un alias de otro comando.)

Si la primera línea no es un Python oficial, crear `python3.exe` junto al Python de python.org
(PowerShell como administrador):

```powershell
Copy-Item "C:\Program Files\Python311\python.exe" "C:\Program Files\Python311\python3.exe"
where.exe python3    # ahora debe salir primero C:\Program Files\Python311\python3.exe
```

Cerrar y volver a abrir VS Code para que coja el PATH actualizado.

### 3.2 Instalar la extensión y ESP-IDF

1. En VS Code, `Ctrl+Shift+X` → buscar **ESP-IDF** (Espressif Systems) → instalar.
2. Si aparece *"No standard ESP-IDF project was found..."*, pulsar **Activate Anyway**.
3. `Ctrl+Shift+P` → **ESP-IDF: Open ESP-IDF Installation Manager**.
4. Elegir el mirror **Github** y la versión **v5.5.5** (última de la serie 5.x; se evitó la v6 por
   precaución, sin haber comprobado si hay incompatibilidades). Dejar la ruta `C:\esp`.
5. Esperar a que termine (~2.85 GB, entre 10 y 45 minutos) y pulsar **Keep** para conservar el
   paquete offline.
6. `Ctrl+Shift+P` → **ESP-IDF: Select Current ESP-IDF Version** → v5.5.5.

### 3.3 Verificar la instalación

Abrir una terminal con el entorno (`Ctrl+Shift+P` → **ESP-IDF: Open ESP-IDF Terminal**). Debe
aparecer `(venv)` al principio de la línea. Después:

```powershell
idf.py --version
```

### 3.4 Si la instalación falló

Error observado en la primera instalación:

```
Failed to install Python environment: failed to install requirements from file
"C:\esp\v5.5.5\esp-idf\tools\requirements\requirements.core.txt":
El sistema no puede encontrar la ruta especificada. (os error 3)
```

Las herramientas se habían instalado bien, pero el log mostraba
`Found python3 on Windows PATH: C:\msys64\ucrt64\bin\python3.exe`. Solución: aplicar el paso 3.1,
borrar lo que quedó a medias y repetir la instalación:

```powershell
Remove-Item -Recurse -Force C:\esp\v5.5.5
Remove-Item -Recurse -Force C:\Espressif\tools\python
```

## 4. Flujo de trabajo

### 4.1 Secuencia completa de un vistazo

```powershell
cd <carpeta-de-trabajo>
idf.py create-project mi_proyecto      # o create-project-from-example (ver 4.3)
cd mi_proyecto
idf.py set-target esp32                # solo la primera vez
idf.py build                           # compilar (no necesita la placa)
idf.py -p COM3 flash monitor           # flashear y ver la salida (necesita la placa)
```

### 4.2 Preparar la sesión

1. **Conectar la placa** por USB con un cable de datos (no solo de carga). Si no aparece ningún
   puerto COM, instalar el driver CP210x o CH340, según el chip USB de la placa.
2. **Averiguar el puerto:**
   ```powershell
   [System.IO.Ports.SerialPort]::GetPortNames()
   ```
3. **Abrir una terminal con el entorno ESP-IDF** (`(venv)` visible):
   `Ctrl+Shift+P` → **ESP-IDF: Open ESP-IDF Terminal**. En cualquier otra PowerShell se puede
   activar con:
   ```powershell
   & 'C:\Espressif\tools\Microsoft.v5.5.5.PowerShell_profile.ps1'
   ```

El entorno solo existe en la terminal donde se activó; al cerrar VS Code hay que repetir este paso.

### 4.3 Crear un proyecto

Ejecutar desde la carpeta que contendrá el proyecto (no desde dentro de otro proyecto) y con el
entorno activo.

**Proyecto vacío:**

```powershell
idf.py create-project mi_proyecto
cd mi_proyecto
code .
```

```
mi_proyecto/
├── CMakeLists.txt
└── main/
    ├── CMakeLists.txt
    └── mi_proyecto.c      <- el código (app_main) va aquí
```

Si se renombra el `.c`, actualizar `main/CMakeLists.txt`:

```cmake
idf_component_register(SRCS "mi_proyecto.c" INCLUDE_DIRS ".")
```

**Proyecto a partir de un ejemplo** (así se creó `hello_world`):

```powershell
idf.py create-project-from-example "espressif/esp-tflite-micro:hello_world"
cd hello_world
```

El formato es `"espacio/componente:ejemplo"`. La primera compilación descarga los componentes que
necesite. Para añadir un componente a un proyecto existente:
`idf.py add-dependency "espressif/esp-tflite-micro"`.

### 4.4 Compilar, flashear y ver la salida

```powershell
idf.py set-target esp32            # solo la primera vez (o al cambiar de chip)
idf.py build
idf.py -p COM3 flash monitor
```

- Si se queda en `Connecting...`, mantener pulsado el botón **BOOT** hasta que empiece a subir.
- Salir del monitor con `Ctrl+]`. En teclado español puede dar `Unknown menu character ']'`; la
  alternativa es `Ctrl+T` y luego `X` (la ayuda del monitor sale con `Ctrl+T` y `Ctrl+H`).
- Para reiniciar la placa sin reflashear, pulsar el botón **EN**.
- **Tras editar el código:** guardar con `Ctrl+S` y repetir `idf.py -p COM3 flash monitor`, que
  recompila lo necesario.
- Con un proyecto abierto en VS Code, la barra inferior tiene iconos para elegir target y puerto y
  para compilar, flashear y abrir el monitor.

## 5. Pruebas realizadas

### 5.1 `blink`: encender y apagar el LED

Proyecto vacío (`idf.py create-project blink`) con este `main/blink.c`:

```c
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define LED_GPIO GPIO_NUM_2

void app_main(void)
{
    gpio_reset_pin(LED_GPIO);
    gpio_set_direction(LED_GPIO, GPIO_MODE_OUTPUT);

    while (1) {
        gpio_set_level(LED_GPIO, 1);
        vTaskDelay(pdMS_TO_TICKS(500));
        gpio_set_level(LED_GPIO, 0);
        vTaskDelay(pdMS_TO_TICKS(500));
    }
}
```

**Resultado:** el LED del GPIO 2 parpadea cada 500 ms. En otras placas el LED puede estar en otro
pin o no existir.

**Incidencia:** el primer flasheo no hacía parpadear nada y el monitor mostraba `Calling app_main()`
seguido de `Returned from app_main()`. Con un `while (1)` infinito eso indicaba que se había
compilado el `app_main` vacío por defecto, porque el archivo no estaba guardado. Se resolvió
guardando con `Ctrl+S` y reflasheando.

### 5.2 `hello_world` de TFLite Micro

Creado con `create-project-from-example` (ver [4.3](#43-crear-un-proyecto)) y ejecutado con la
secuencia de [4.4](#44-compilar-flashear-y-ver-la-salida).

El modelo es una red neuronal minúscula que recibe un ángulo `x` (radianes) y devuelve una
aproximación de `sin(x)`. Es una demostración del flujo completo (modelo `.tflite` → firmware →
inferencia en el chip), no un modelo preciso.

**Datos del build y del arranque**

| Dato | Valor |
|---|---|
| Tamaño de `hello_world.bin` | 187 072 bytes (90 % libre en la partición de 1.9 MB) |
| Frecuencia de CPU en ejecución | 160 MHz (el chip admite 240 MHz) |
| Flash | 4 MB, modo QIO, 80 MHz |
| Salida | Ciclos idénticos de 20 puntos, de `x = 0` a `x ≈ 5.97` |

**Resultados.** El modelo es determinista: cada ciclo repite exactamente los mismos 20 valores. Los
de un ciclo están en [`hello_world_results.csv`](hello_world_results.csv).

![Salida del modelo frente a sin(x)](hello_world_plot.png)

| Métrica | Valor |
|---|---|
| Error absoluto medio (MAE) | 0.037 |
| Error máximo | 0.110 en `x = 4.712` (3π/2) |
| Máximo del modelo | 1.042 en `x = 1.571` (real: 1.0) |
| Mínimo del modelo | -1.110 en `x = 4.712` (real: -1.0) |

La curva tiene la forma correcta, con errores de hasta un 11 %. Todas las salidas son múltiplos
enteros de ≈0.00847, lo que indica que el modelo trabaja con salida cuantizada a INT8; junto con su
tamaño minúsculo, explica ese error.

Para regenerar la gráfica a partir del CSV:

```powershell
pip install numpy pandas matplotlib
python plot_results.py
```

**Archivos de esta prueba:** `hello_world_results.csv`, `plot_results.py`, `hello_world_plot.png`.

## 6. Referencia rápida

### 6.1 Comandos de `idf.py`

| Comando | Qué hace |
|---|---|
| `idf.py create-project nombre` | Crea un proyecto vacío |
| `idf.py create-project-from-example "espacio/componente:ejemplo"` | Crea un proyecto desde un ejemplo del registro |
| `idf.py add-dependency "espacio/componente"` | Añade un componente al proyecto |
| `idf.py set-target esp32` | Fija el chip destino (`esp32s3`, `esp32c3`...) |
| `idf.py menuconfig` | Menú de configuración (flash, CPU, particiones...) |
| `idf.py build` | Compila |
| `idf.py -p COM3 flash` | Sube el firmware |
| `idf.py -p COM3 monitor` | Abre el monitor serie |
| `idf.py -p COM3 flash monitor` | Flashea y abre el monitor |
| `idf.py -p COM3 -b 115200 flash` | Flashea a menor velocidad (útil si falla a 460800) |
| `idf.py size` | Tamaño de la aplicación en flash y RAM |
| `idf.py clean` / `idf.py fullclean` | Borra lo compilado / toda la carpeta `build` (usar al cambiar de target) |
| `idf.py erase-flash` | Borra toda la flash de la placa |
| `idf.py --help` | Lista todos los comandos |

### 6.2 Información de la placa (esptool)

```powershell
esptool.py chip_id      # modelo de chip, características y MAC (en versiones nuevas: esptool chip-id)
esptool.py flash_id     # fabricante y tamaño de la flash
```

Añadir `-p COM3` si hay varias placas conectadas.

### 6.3 Problemas frecuentes

| Síntoma | Causa probable | Solución |
|---|---|---|
| `idf.py` no se reconoce | Terminal sin el entorno ESP-IDF | Abrir con **ESP-IDF: Open ESP-IDF Terminal** o ejecutar el script de la sección [4.2](#42-preparar-la-sesión) |
| Menú lateral y barra inferior de la extensión vacíos | Carpeta equivocada abierta | **File → Open Folder** sobre la carpeta que contiene `CMakeLists.txt` y `main/` |
| No aparece ningún puerto COM | Falta el driver o el cable es solo de carga | Instalar CP210x o CH340; probar otro cable |
| `Connecting......` sin avanzar | La placa no entra en modo de descarga | Mantener pulsado **BOOT** al empezar a flashear |
| Falla el flasheo a 460800 baudios | Cable o driver poco fiables | Usar `-b 115200` |
| Compila y flashea, pero no hace nada | Código sin guardar o `app_main` vacío | `Ctrl+S`, recompilar y reflashear |
| Error tras cambiar de chip | Restos de la compilación anterior | `idf.py fullclean` y luego `set-target` |
| Subrayado rojo en `#include "driver/gpio.h"` | Solo el autocompletado (IntelliSense); no afecta a la compilación | Compilar una vez y ejecutar **ESP-IDF: Add VS Code Configuration Folder** |

## 7. Qué se puede ejecutar en un ESP32

### 7.1 LLM (texto)

Todos parten de [llama2.c](https://github.com/karpathy/llama2.c) de Karpathy y requieren un ESP32-S3
con PSRAM. No sirven como chatbot: generan cuentos cortos.

| Proyecto | Descripción |
|---|---|
| [DaveBben/esp32-llm](https://github.com/DaveBben/esp32-llm) | Modelo de 260K parámetros, 19 tok/s usando ambos núcleos y ESP-DSP |
| [doryiii/esp32-llm](https://github.com/doryiii/esp32-llm) | Soporta INT8 y F32; el modelo de 3.3M va a unos 12 tok/s |
| [slvDev/esp32-ai](https://github.com/slvDev/esp32-ai) | Modelo de 28.9M parámetros a 9.88 tok/s, casi todo en flash (Per-Layer Embeddings) |

### 7.2 Visión y audio

| Proyecto | Descripción |
|---|---|
| [espressif/esp-dl](https://github.com/espressif/esp-dl) | Inferencia de Espressif con modelos ya cuantizados (caras, gestos, YOLO11n, YOLO26). Para S3 y P4 |
| [esp-tflite-micro](https://components.espressif.com/components/espressif/esp-tflite-micro) | TFLite Micro para ESP32. Ejemplos: `hello_world`, `micro_speech` (palabras clave), `person_detection` |
| [ESP-WHO](https://developer.espressif.com/blog/2026/05/esp-who-get-started/) | Framework de visión sobre ESP-DL (S3 y P4) |

### 7.3 Cuantización

TensorRT solo funciona con GPUs de NVIDIA y no aplica aquí. Los equivalentes son:

- **TFLite / LiteRT Micro:** convertir a `.tflite` INT8. No todos los operadores están soportados,
  así que convertir no garantiza que el modelo corra.
- **ESP-PPQ:** cuantiza desde ONNX al formato `.espdl` para ESP-DL.
- **Edge Impulse:** entrena, cuantiza y exporta con poco código.
- [tinyml-deployer](https://pypi.org/project/tinyml-deployer/): analiza compatibilidad, cuantiza y
  genera el proyecto ESP-IDF.

En Hugging Face no se encontraron repositorios específicos de ESP32; los checkpoints `tinyllamas`
que usan los proyectos de LLM sí están allí.

## 8. Próximos pasos

### 8.1 Medir el rendimiento del `hello_world`

Objetivo: obtener el tiempo de inferencia y la memoria que usa el modelo.

<details>
<summary>Cambios en <code>main/main_functions.cc</code></summary>

Añadir arriba del archivo:

```cpp
#include "esp_timer.h"
#include "esp_system.h"
```

Añadir al final de `setup()`, después de reservar los tensores (`AllocateTensors()`):

```cpp
MicroPrintf("Arena usada: %d de %d bytes",
            (int)interpreter->arena_used_bytes(), kTensorArenaSize);
MicroPrintf("Heap libre: %d bytes", (int)esp_get_free_heap_size());

const int N = 1000;
int64_t t0 = esp_timer_get_time();
for (int i = 0; i < N; i++) {
  interpreter->Invoke();
}
int64_t t1 = esp_timer_get_time();
MicroPrintf("Inferencia media: %d us (%d ejecuciones)", (int)((t1 - t0) / N), N);
```

Ejecutar 1000 veces y promediar da una medida más fiable que una sola inferencia, que dura
microsegundos. Si el compilador no encuentra `esp_timer.h`, añadir `PRIV_REQUIRES esp_timer` en
`main/CMakeLists.txt`. Después: `idf.py -p COM3 flash monitor`.

</details>

`idf.py size` da además el uso estático de flash y RAM. Otro experimento útil: repetir la medida a
240 MHz (`idf.py menuconfig` → *Component config* → *ESP System Settings* → *CPU frequency*).

### 8.2 Un modelo propio: dígitos 8x8

Propuesta: clasificar los dígitos del dataset `digits` de scikit-learn (imágenes de 8x8 píxeles)
con una red pequeña (64 → 32 → 10, unos 2.4 mil parámetros, ~2.5 KB en INT8). No necesita hardware
extra y permite comprobar si la cuantización y el chip mantienen la precisión.

1. **Entrenar** el modelo en el PC con Keras y medir la precisión en float.
2. **Convertir a TFLite INT8** con un dataset representativo y medir la precisión del modelo
   cuantizado en el PC.
3. **Exportar** el `.tflite` a un array C e integrarlo en un proyecto `esp-tflite-micro` (partiendo
   del `hello_world`, cambiando el modelo y los operadores registrados).
4. **Ejecutar en el ESP32** el conjunto de test completo (unas 360 muestras caben en flash),
   calcular la precisión y la latencia media en el chip y compararlas con las del PC.

Conviene instalar TensorFlow en un entorno virtual aparte, sin tocar el de ESP-IDF.

### 8.3 Ampliar el hardware

- **Acelerómetro/giroscopio MPU6050** (unos 2 €): reconocimiento de gestos con el mismo flujo que
  el punto anterior.
- **ESP32-S3 con cámara** (por ejemplo, XIAO ESP32S3 Sense): `person_detection`, ESP-WHO o los LLM
  diminutos.
- **Micrófono I2S:** `micro_speech` (palabras clave).

### 8.4 Ajustes pendientes

Los avisos del log de arranque indican dos ajustes: la flash detectada es de 4 MB pero `blink` se
compiló para 2 MB, y se está usando el driver genérico para una flash Boya. Se corrigen en
`idf.py menuconfig`, activando `SPI_FLASH_SUPPORT_BOYA_CHIP` y fijando el tamaño de flash.
