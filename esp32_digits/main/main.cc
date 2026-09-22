// Clasificador de dígitos 8x8 en ESP32 con TensorFlow Lite Micro.
//
// Carga el modelo generado por train_and_convert.py (model_data.cc/.h),
// ejecuta la inferencia sobre las muestras de test.h de test_samples.h y
// muestra por el monitor serie la predicción, el acierto y el tiempo medio
// de inferencia.

#include <cstdio>

#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_log.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/micro/system_setup.h"
#include "tensorflow/lite/schema/schema_generated.h"

#include "model_data.h"
#include "test_samples.h"

namespace {
// Tamaño del "arena" de trabajo para tensores intermedios. El modelo es
// pequeño (unos 2.4 KB de pesos), 20 KB da margen de sobra. Si falla
// AllocateTensors(), subir este valor; si interpreter.arena_used_bytes()
// sale mucho menor, se puede bajar.
constexpr int kTensorArenaSize = 20 * 1024;
alignas(16) uint8_t tensor_arena[kTensorArenaSize];
}  // namespace

extern "C" void app_main(void) {
  tflite::InitializeTarget();

  const tflite::Model* model = tflite::GetModel(g_digits_model_data);
  if (model->version() != TFLITE_SCHEMA_VERSION) {
    MicroPrintf("Version del modelo (%d) distinta de la soportada (%d)",
                model->version(), TFLITE_SCHEMA_VERSION);
    return;
  }

  // Solo se registran las operaciones que usa este modelo (Dense + ReLU +
  // Softmax). Si al compilar TFLite Micro se queja de un operador que
  // falta, añadirlo aquí con resolver.AddXxx() y subir el número entre
  // <> a juego.
  static tflite::MicroMutableOpResolver<3> resolver;
  resolver.AddFullyConnected();
  resolver.AddRelu();
  resolver.AddSoftmax();

  static tflite::MicroInterpreter interpreter(model, resolver, tensor_arena,
                                               kTensorArenaSize);

  if (interpreter.AllocateTensors() != kTfLiteOk) {
    MicroPrintf("Fallo al reservar los tensores (sube kTensorArenaSize)");
    return;
  }

  MicroPrintf("Arena usada: %d de %d bytes",
              (int)interpreter.arena_used_bytes(), kTensorArenaSize);

  TfLiteTensor* input = interpreter.input(0);
  TfLiteTensor* output = interpreter.output(0);

  int correct = 0;
  int64_t total_us = 0;

  for (int i = 0; i < NUM_TEST_SAMPLES; i++) {
    for (int j = 0; j < INPUT_SIZE; j++) {
      input->data.int8[j] = g_test_input[i][j];
    }

    int64_t t0 = esp_timer_get_time();
    TfLiteStatus status = interpreter.Invoke();
    int64_t t1 = esp_timer_get_time();

    if (status != kTfLiteOk) {
      MicroPrintf("Fallo al ejecutar la inferencia %d", i);
      continue;
    }
    total_us += (t1 - t0);

    // La salida es SOFTMAX cuantizado a INT8. El argmax coincide con el
    // de la salida en float, así que no hace falta deshacer la
    // cuantización para clasificar.
    int8_t best_score = output->data.int8[0];
    int best_idx = 0;
    for (int c = 1; c < 10; c++) {
      if (output->data.int8[c] > best_score) {
        best_score = output->data.int8[c];
        best_idx = c;
      }
    }

    bool ok = (best_idx == g_test_labels[i]);
    correct += ok ? 1 : 0;
    MicroPrintf("Muestra %2d -> prediccion=%d  real=%d  %s", i, best_idx,
                g_test_labels[i], ok ? "OK" : "FALLO");
  }

  MicroPrintf("");
  MicroPrintf("Precision en el ESP32: %d/%d (%.1f%%)", correct,
              NUM_TEST_SAMPLES, 100.0 * correct / NUM_TEST_SAMPLES);
  MicroPrintf("Tiempo medio de inferencia: %d us",
              (int)(total_us / NUM_TEST_SAMPLES));

  while (true) {
    vTaskDelay(pdMS_TO_TICKS(1000));
  }
}