# comparativa-arquitecturas-iot
codigo fuente comparativa-arquitecturas-iot
# TFM: Comparativa de Arquitecturas IoT para Agricultura de Precisión

Este repositorio contiene el código fuente completo del Trabajo Fin de Máster (TFM) titulado **"Comparativa de arquitecturas de mensajería IoT (broker vs. brokerless) para la transmisión de datos y análisis de imágenes en agricultura de precisión de bajo coste"**.

## 📁 Estructura del Código

*   **`esp32`**: Contiene el firmware para el ESP32-S3.
    *   `main.py`: Bucle principal y lógica de captura.
*   **`servidor`**: Contiene el script para el servidor VPS.
    *   `monitor_cultivos.py`: Servidor Flask que recibe los datos e imagenes.
      
## ⚙️ Requisitos y Tecnologías

*   MicroPython en ESP32-S3.
*   Python 3 en el servidor.
*   Librerías: `umqtt.simple`, `paho-mqtt`, `Flask`, `pika`.

## 🚀 Cómo Usarlo

1.  Carga el firmware del archivo `main.py` en tu placa ESP32-S3.
2.  Despliega el script del archivo `monitor_cultivo.py` en tu VPS.
3.  Ajusta las variables de configuración (IPs, credenciales) según tu entorno.
4.  Ejecuta el script principal en el ESP32 para comenzar la captura y transmisión de datos.
