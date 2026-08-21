# comparativa-arquitecturas-iot
codigo fuente comparativa-arquitecturas-iot
# TFM: Comparativa de Arquitecturas IoT para Agricultura de Precisión

Este repositorio contiene el código fuente completo del Trabajo Fin de Máster (TFM) titulado **"Comparativa de arquitecturas de mensajería IoT (broker vs. brokerless) para la transmisión de datos y análisis de imágenes en agricultura de precisión de bajo coste"**.

## 📁 Estructura del Código

*   **`esp32/`**: Contiene el firmware para el ESP32-S3.
    *   `main.py`: Bucle principal y lógica de captura.
    *   `zeromq_client.py`: Cliente ZeroMQ (TCP directo).
    *   `mqtt_client.py`: Cliente MQTT.
    *   `rabbitmq_client.py`: Cliente HTTP para RabbitMQ.
    *   `telegram.py`: Envío de notificaciones a Telegram.
*   **`servidor/`**: Contiene los scripts para el servidor VPS.
    *   `zeromq_server.py`: Servidor TCP para ZeroMQ.
    *   `rabbitmq_gateway.py`: Pasarela HTTP con Flask y pika.
    *   `metricas_listener.py`: Receptor de métricas de latencia.

## ⚙️ Requisitos y Tecnologías

*   MicroPython en ESP32-S3.
*   Python 3 en el servidor.
*   Librerías: `umqtt.simple`, `paho-mqtt`, `Flask`, `pika`.

## 🚀 Cómo Usarlo

1.  Carga el firmware de la carpeta `esp32/` en tu placa ESP32-S3.
2.  Despliega los scripts de la carpeta `servidor/` en tu VPS.
3.  Ajusta las variables de configuración (IPs, credenciales) según tu entorno.
4.  Ejecuta el script principal en el ESP32 para comenzar la captura y transmisión de datos.
