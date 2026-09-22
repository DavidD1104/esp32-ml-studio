"""
Entrena un clasificador de dígitos manuscritos 8x8 (dataset `digits` de
scikit-learn), lo cuantiza a INT8 con TensorFlow Lite y genera los archivos
C que se copian en el proyecto ESP-IDF (carpeta `esp32_project/main/`).

Ejecutar en un entorno virtual DISTINTO al de ESP-IDF, para no mezclar
paquetes:

    python -m venv venv_tf
    venv_tf\\Scripts\\activate        (Windows)
    pip install tensorflow scikit-learn numpy
    python train_and_convert.py

Genera en esta misma carpeta:
    digits_model.tflite   modelo cuantizado, por si se quiere inspeccionar
    model_data.cc/.h      el modelo como array C (esto es lo que va al ESP32)
    test_samples.h        unas muestras de test, ya cuantizadas, para
                           comprobar la precisión en el propio chip
"""

import os
os.environ["KERAS_BACKEND"] = "tensorflow"  # evita que Keras 3 intente importar jax

import numpy as np
from sklearn.datasets import load_digits
from sklearn.model_selection import train_test_split
import tensorflow as tf

SEED = 42
np.random.seed(SEED)
tf.random.set_seed(SEED)

# ---------------------------------------------------------------------------
# 1. Datos: 1797 imágenes de 8x8 (64 píxeles), dígitos 0-9
# ---------------------------------------------------------------------------
digits = load_digits()
X = digits.data.astype(np.float32) / 16.0  # los píxeles van de 0 a 16
y = digits.target.astype(np.int32)

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=SEED, stratify=y
)
print(f"Train: {X_train.shape[0]} muestras · Test: {X_test.shape[0]} muestras")

# ---------------------------------------------------------------------------
# 2. Modelo: 64 -> 32 (ReLU) -> 10 (softmax). Unos 2400 parámetros.
# ---------------------------------------------------------------------------
model = tf.keras.Sequential([
    tf.keras.layers.Input(shape=(64,)),
    tf.keras.layers.Dense(32, activation="relu"),
    tf.keras.layers.Dense(10, activation="softmax"),
])
model.compile(optimizer="adam", loss="sparse_categorical_crossentropy",
              metrics=["accuracy"])
model.summary()

model.fit(X_train, y_train, validation_split=0.1, epochs=60, batch_size=16,
          verbose=2)

loss, acc = model.evaluate(X_test, y_test, verbose=0)
print(f"\nPrecisión en float32 (PC): {acc:.4f}")

# ---------------------------------------------------------------------------
# 3. Cuantizar a INT8 (entrada y salida incluidas, para TFLite Micro)
# ---------------------------------------------------------------------------
def representative_dataset():
    for i in range(min(200, len(X_train))):
        yield [X_train[i:i + 1]]


converter = tf.lite.TFLiteConverter.from_keras_model(model)
converter.optimizations = [tf.lite.Optimize.DEFAULT]
converter.representative_dataset = representative_dataset
converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
converter.inference_input_type = tf.int8
converter.inference_output_type = tf.int8

tflite_model = converter.convert()

with open("digits_model.tflite", "wb") as f:
    f.write(tflite_model)
print(f"\nModelo .tflite guardado: {len(tflite_model)} bytes")

# ---------------------------------------------------------------------------
# 4. Evaluar el modelo ya cuantizado (simulado en el PC, con el intérprete
#    de TFLite normal, no TFLite Micro). Sirve para comparar con lo que
#    luego mida el ESP32.
# ---------------------------------------------------------------------------
interpreter = tf.lite.Interpreter(model_content=tflite_model)
interpreter.allocate_tensors()
input_details = interpreter.get_input_details()[0]
output_details = interpreter.get_output_details()[0]

in_scale, in_zero = input_details["quantization"]

correct = 0
for i in range(len(X_test)):
    x_q = np.round(X_test[i] / in_scale + in_zero).astype(np.int8).reshape(1, -1)
    interpreter.set_tensor(input_details["index"], x_q)
    interpreter.invoke()
    out = interpreter.get_tensor(output_details["index"])[0]
    if np.argmax(out) == y_test[i]:
        correct += 1

acc_int8 = correct / len(X_test)
print(f"Precisión en INT8 (simulada en PC): {acc_int8:.4f}")
print(f"Cuantización de la entrada: scale={in_scale:.6f}, zero_point={in_zero}")

# ---------------------------------------------------------------------------
# 5. Exportar el modelo como array C (model_data.cc / model_data.h)
# ---------------------------------------------------------------------------
def to_c_array(data: bytes, var_name: str) -> str:
    bytes_per_line = 16
    lines = []
    for i in range(0, len(data), bytes_per_line):
        chunk = data[i:i + bytes_per_line]
        lines.append("  " + ", ".join(f"0x{b:02x}" for b in chunk) + ",")
    body = "\n".join(lines)
    return (
        "// Generado automáticamente por train_and_convert.py. No editar a mano.\n"
        '#include "model_data.h"\n\n'
        f"alignas(16) const unsigned char {var_name}[] = {{\n{body}\n}};\n"
        f"const unsigned int {var_name}_len = {len(data)};\n"
    )


with open("model_data.cc", "w") as f:
    f.write(to_c_array(tflite_model, "g_digits_model_data"))

with open("model_data.h", "w") as f:
    f.write(
        "#ifndef MODEL_DATA_H_\n#define MODEL_DATA_H_\n\n"
        "extern const unsigned char g_digits_model_data[];\n"
        "extern const unsigned int g_digits_model_data_len;\n\n"
        "#endif  // MODEL_DATA_H_\n"
    )

print("Generados model_data.cc y model_data.h")

# ---------------------------------------------------------------------------
# 6. Exportar unas muestras de test, ya cuantizadas a INT8, para probarlas
#    directamente en el ESP32 sin necesitar más Python en el chip.
# ---------------------------------------------------------------------------
N_SAMPLES = 20
sel = np.random.choice(len(X_test), N_SAMPLES, replace=False)

rows = []
labels = []
for idx in sel:
    x_q = np.round(X_test[idx] / in_scale + in_zero).astype(np.int8)
    vals = ", ".join(str(int(v)) for v in x_q)
    rows.append(f"  {{ {vals} }}")
    labels.append(str(int(y_test[idx])))

with open("test_samples.h", "w") as f:
    f.write(
        "// Generado automáticamente por train_and_convert.py. No editar a mano.\n"
        "#ifndef TEST_SAMPLES_H_\n#define TEST_SAMPLES_H_\n\n"
        f"#define NUM_TEST_SAMPLES {N_SAMPLES}\n"
        "#define INPUT_SIZE 64\n\n"
        f"const signed char g_test_labels[NUM_TEST_SAMPLES] = {{ {', '.join(labels)} }};\n\n"
        "const signed char g_test_input[NUM_TEST_SAMPLES][INPUT_SIZE] = {\n"
        + ",\n".join(rows) + "\n};\n\n"
        "#endif  // TEST_SAMPLES_H_\n"
    )

print(f"Generado test_samples.h con {N_SAMPLES} muestras de test")
print("\nListo. Copia model_data.cc, model_data.h y test_samples.h a")
print("esp32_project/main/, y sigue el README de esa carpeta.")
