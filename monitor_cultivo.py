"""
SERVIDOR TFM - COMPARATIVA DE ARQUITECTURAS IoT
ZeroMQ(TCP), MQTT, RabbitMQ + Telegram
Crea filas Telegram automáticamente
"""

from flask import Flask, request, render_template_string, send_from_directory
import os
import socket
import threading
import csv
import subprocess
import pandas as pd
from datetime import datetime

app = Flask(__name__)

CARPETA_FOTOS = "/home/opc/fotos_cultivo"
PUERTO_WEB = 5002
PUERTO_ZEROMQ = 9999
PUERTO_MQTT = 1883
PUERTO_METRICAS = 9998
ARCHIVO_CSV = "/home/opc/metricas_tfm.csv"
ARCHIVO_EXCEL = "/home/opc/metricas_tfm.xlsx"

os.makedirs(CARPETA_FOTOS, exist_ok=True)

if not os.path.exists(ARCHIVO_CSV):
    with open(ARCHIVO_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'timestamp', 'foto_num', 'arquitectura', 'tamano_bytes',
            'tamano_kb', 'latencia_ms', 'exito', 'luz_aec_value',
            'modo_dia_noche', 'resolucion'
        ])

print("=" * 60)
print("🎓 SERVIDOR TFM - COMPARATIVA ARQUITECTURAS IoT")
print("=" * 60)

contador_global = 0

def guardar_metrica(timestamp, foto_num, arquitectura, tamano, latencia, exito, luz, modo):
    with open(ARCHIVO_CSV, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            timestamp, foto_num, arquitectura, tamano,
            round(tamano/1024, 1), latencia, 1 if exito else 0,
            luz, modo, "1600x1200"
        ])
    print(f"  📊 {arquitectura} | {tamano}B | {latencia}ms | {'✅' if exito else '❌'}")

def guardar_foto(data, arquitectura, foto_num):
    fecha_actual = datetime.now().strftime('%Y-%m-%d')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    carpeta_dia = os.path.join(CARPETA_FOTOS, fecha_actual)
    os.makedirs(carpeta_dia, exist_ok=True)
    nombre = f"{carpeta_dia}/cultivo_{timestamp}_{arquitectura}_{foto_num:04d}.jpg"
    with open(nombre, 'wb') as f:
        f.write(data)
    return nombre

def exportar_excel():
    try:
        if os.path.exists(ARCHIVO_CSV):
            df = pd.read_csv(ARCHIVO_CSV)
            df.to_excel(ARCHIVO_EXCEL, index=False)
    except: pass

def obtener_metricas():
    metricas = []
    if os.path.exists(ARCHIVO_CSV):
        with open(ARCHIVO_CSV, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                metricas.append(row)
    return metricas

def obtener_estadisticas():
    stats = {}
    for m in obtener_metricas():
        arq = m['arquitectura']
        if arq not in stats:
            stats[arq] = {'total': 0, 'exitos': 0, 'fallos': 0, 'latencias': [], 'tamanos': []}
        stats[arq]['total'] += 1
        if m['exito'] == '1' and float(m['latencia_ms']) > 0:
            stats[arq]['exitos'] += 1
            stats[arq]['latencias'].append(float(m['latencia_ms']))
            stats[arq]['tamanos'].append(float(m['tamano_kb']))
        elif m['exito'] == '1':
            stats[arq]['exitos'] += 1
        else:
            stats[arq]['fallos'] += 1
    for arq in stats:
        if stats[arq]['latencias']:
            stats[arq]['latencia_media'] = round(sum(stats[arq]['latencias']) / len(stats[arq]['latencias']), 1)
            stats[arq]['tamano_medio'] = round(sum(stats[arq]['tamanos']) / len(stats[arq]['tamanos']), 1)
        else:
            stats[arq]['latencia_media'] = 0
            stats[arq]['tamano_medio'] = 0
    return stats

HTML = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="refresh" content="30"><title>🎓 TFM - Comparativa IoT</title>
    <style>
        :root { --bg: #0d1117; --card: #161b22; --accent: #58a6ff; --green: #3fb950; --yellow: #d2991d; --purple: #a371f7; --blue: #58a6ff; --text: #c9d1d9; --muted: #8b949e; }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Arial, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }
        .header { background: var(--card); padding: 20px; text-align: center; border-bottom: 2px solid var(--accent); }
        .header h1 { color: var(--accent); font-size: 1.5em; }
        .container { max-width: 1500px; margin: 0 auto; padding: 20px; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin-bottom: 25px; }
        .stat-card { background: var(--card); border-radius: 12px; padding: 20px; text-align: center; border: 1px solid #30363d; }
        .stat-card h3 { font-size: 0.85em; margin-bottom: 8px; }
        .stat-card .value { font-size: 2em; font-weight: 700; }
        .stat-card .sub { font-size: 0.75em; color: var(--muted); margin-top: 4px; }
        .zeromq h3 { color: #3fb950; } .zeromq .value { color: #3fb950; }
        .mqtt h3 { color: #d2991d; } .mqtt .value { color: #d2991d; }
        .rabbitmq h3 { color: #a371f7; } .rabbitmq .value { color: #a371f7; }
        .telegram h3 { color: #58a6ff; } .telegram .value { color: #58a6ff; }
        .panel { background: var(--card); border-radius: 12px; padding: 20px; margin-bottom: 20px; border: 1px solid #30363d; }
        .panel h2 { color: var(--accent); font-size: 1.1em; margin-bottom: 15px; }
        .tabla-metricas { width: 100%; border-collapse: collapse; font-size: 0.8em; }
        .tabla-metricas th { background: #21262d; padding: 10px; text-align: left; color: var(--accent); }
        .tabla-metricas td { padding: 8px 10px; border-bottom: 1px solid #30363d; }
        .galeria { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
        .card { background: #0d1117; border-radius: 10px; overflow: hidden; border: 1px solid #30363d; cursor: pointer; transition: transform 0.2s; }
        .card:hover { transform: scale(1.03); }
        .card img { width: 100%; height: 180px; object-fit: cover; }
        .card .info { padding: 8px; font-size: 0.7em; text-align: center; }
        .card.zeromq { border-bottom: 3px solid #3fb950; }
        .card.mqtt { border-bottom: 3px solid #d2991d; }
        .card.rabbitmq { border-bottom: 3px solid #a371f7; }
        .card.telegram { border-bottom: 3px solid #58a6ff; }
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.95); z-index: 1000; cursor: pointer; }
        .modal img { max-width: 95%; max-height: 95%; position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); border-radius: 10px; }
        .modal .close { position: absolute; top: 20px; right: 30px; color: #fff; font-size: 40px; cursor: pointer; }
        @media (max-width: 768px) { .galeria { grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); } }
    </style>
</head>
<body>
    <div class="header"><h1>🎓 TFM - Comparativa de Arquitecturas IoT</h1><p>{{ total }} fotos | {{ ahora }}</p></div>
    <div class="container">
        <div class="stats">
            {% for arq, s in stats.items() %}
            <div class="stat-card {{ arq.lower() }}"><h3>{{ arq }}</h3><div class="value">{{ s.latencia_media }} ms</div><div class="sub">{{ s.exitos }}/{{ s.total }} éxitos | {{ s.tamano_medio }} KB</div></div>
            {% endfor %}
        </div>
        <div class="panel"><h2>📊 Últimas 10 Métricas</h2><div style="overflow-x:auto;"><table class="tabla-metricas"><tr><th>Hora</th><th>#</th><th>Arquitectura</th><th>Tamaño</th><th>RTT</th><th>Éxito</th></tr>
            {% for m in ultimas_metricas[:10] %}<tr><td>{{ m.timestamp[-8:] if m.timestamp|length > 8 else m.timestamp }}</td><td>{{ m.foto_num }}</td><td style="color:{% if 'ZeroMQ' in m.arquitectura %}#3fb950{% elif 'MQTT' in m.arquitectura %}#d2991d{% elif 'Telegram' in m.arquitectura %}#58a6ff{% else %}#a371f7{% endif %}">{{ m.arquitectura }}</td><td>{{ m.tamano_kb }} KB</td><td>{{ m.latencia_ms }} ms</td><td>{{ '✅' if m.exito == '1' else '❌' }}</td></tr>{% endfor %}
        </table></div></div>
        <div class="panel"><h2>📷 Últimas 5 Fotos</h2><div class="galeria">
            {% for foto in fotos[:5] %}<div class="card {{ foto.arq_class }}" onclick="abrirModal('{{ foto.ruta }}')"><img src="{{ foto.ruta }}" loading="lazy" /><div class="info">{{ foto.arquitectura }}<br>{{ foto.fecha }}</div></div>{% endfor %}
        </div></div>
    </div>
    <div class="modal" id="modal" onclick="this.style.display='none'"><span class="close">&times;</span><img id="modal-img" src="" /></div>
    <script>function abrirModal(r) { document.getElementById('modal-img').src=r; document.getElementById('modal').style.display='block'; }</script>
</body>
</html>"""

@app.route('/')
def panel():
    exportar_excel()
    stats = obtener_estadisticas()
    metricas = obtener_metricas()
    ultimas = metricas[-10:] if len(metricas) > 10 else metricas
    ultimas.reverse()
    fotos = []
    if os.path.exists(CARPETA_FOTOS):
        for carpeta in sorted(os.listdir(CARPETA_FOTOS), reverse=True):
            ruta_c = os.path.join(CARPETA_FOTOS, carpeta)
            if os.path.isdir(ruta_c):
                for archivo in sorted(os.listdir(ruta_c), reverse=True)[:5]:
                    if archivo.endswith('.jpg'):
                        partes = archivo.replace('.jpg','').split('_')
                        arq = partes[2] if len(partes) > 2 else 'DESC'
                        fecha = f"{partes[1][4:6]}/{partes[1][6:8]} {partes[1][8:10]}:{partes[1][10:12]}" if len(partes) > 1 else ''
                        arq_class = 'zeromq' if 'ZeroMQ' in arq else ('mqtt' if 'MQTT' in arq else ('telegram' if 'Telegram' in arq else 'rabbitmq'))
                        fotos.append({'ruta': f'/fotos/{carpeta}/{archivo}', 'arquitectura': arq, 'fecha': fecha, 'arq_class': arq_class})
    return render_template_string(HTML, stats=stats, ultimas_metricas=ultimas, fotos=fotos, total=len(metricas), ahora=datetime.now().strftime('%d/%m/%Y %H:%M:%S'))

@app.route('/fotos/<path:ruta>')
def servir_foto(ruta):
    return send_from_directory(CARPETA_FOTOS, ruta)

@app.route('/api/foto', methods=['POST'])
def recibir_foto_rabbitmq():
    global contador_global
    tamano = 0
    if request.is_json:
        datos = request.get_json()
        tamano = datos.get('size', 0)
    elif 'foto' in request.files:
        foto = request.files['foto']
        data = foto.read()
        tamano = len(data)
    contador_global += 1
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    guardar_metrica(timestamp, contador_global, "RabbitMQ", tamano, 0, True, 0, "N/A")
    print(f"[RabbitMQ] #{contador_global}: {tamano}B")
    return "OK", 200

def servidor_zeromq():
    global contador_global
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('0.0.0.0', PUERTO_ZEROMQ))
    sock.listen(1)
    print(f"[ZeroMQ] Puerto {PUERTO_ZEROMQ}")
    while True:
        try:
            conn, addr = sock.accept()
            conn.settimeout(30)
            size_bytes = conn.recv(4)
            img_size = int.from_bytes(size_bytes, 'big')
            data = b''
            while len(data) < img_size:
                chunk = conn.recv(min(4096, img_size - len(data)))
                if not chunk: break
                data += chunk
            if len(data) == img_size and img_size > 0:
                contador_global += 1
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                nombre = guardar_foto(data, "ZeroMQ", contador_global)
                guardar_metrica(timestamp, contador_global, "ZeroMQ", len(data), 0, True, 0, "N/A")
                print(f"[ZeroMQ] #{contador_global}: {len(data)}B → {nombre}")
            conn.send(b'OKOK')
            conn.close()
        except Exception as e:
            print(f"[ZeroMQ] Error: {e}")
            try: conn.close()
            except: pass

def servidor_mqtt():
    global contador_global
    import paho.mqtt.client as mqtt
    def on_connect(client, userdata, flags, rc):
        print(f"[MQTT] Conectado al broker")
        client.subscribe("cultivo/foto")
    def on_message(client, userdata, msg):
        global contador_global
        data = msg.payload
        contador_global += 1
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        nombre = guardar_foto(data, "MQTT", contador_global)
        guardar_metrica(timestamp, contador_global, "MQTT", len(data), 0, True, 0, "N/A")
        print(f"[MQTT] #{contador_global}: {len(data)}B → {nombre}")
        client.publish("cultivo/respuesta", "OK")
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect("localhost", PUERTO_MQTT, 60)
    print(f"[MQTT] Suscrito a cultivo/foto | Responde en cultivo/respuesta")
    client.loop_forever()

def servidor_metricas():
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('0.0.0.0', PUERTO_METRICAS))
    sock.listen(1)
    print(f"[Métricas] Puerto {PUERTO_METRICAS}")
    
    while True:
        try:
            conn, addr = sock.accept()
            conn.settimeout(5)
            data = conn.recv(128).decode().strip()
            conn.close()
            
            partes = data.split('|')
            if len(partes) == 3:
                arq, num_foto, latencia = partes
                
                if os.path.exists(ARCHIVO_CSV):
                    filas = []
                    with open(ARCHIVO_CSV, 'r', encoding='utf-8') as f:
                        reader = csv.reader(f)
                        filas = list(reader)
                    
                    actualizado = False
                    for i in range(len(filas)-1, 0, -1):
                        if len(filas[i]) >= 6 and filas[i][2] == arq and filas[i][5] == '0':
                            filas[i][5] = latencia
                            print(f"  📏 {arq} #{num_foto}: RTT={latencia}ms (fila {i})")
                            actualizado = True
                            break
                    
                    if not actualizado:
                        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        filas.append([timestamp, num_foto, arq, '0', '0', latencia, '1', '0', 'N/A', '1600x1200'])
                        print(f"  📏 {arq} #{num_foto}: RTT={latencia}ms (nueva fila creada)")
                    
                    with open(ARCHIVO_CSV, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        writer.writerows(filas)
                    exportar_excel()
        except Exception as e:
            try: conn.close()
            except: pass

if __name__ == '__main__':
    threading.Thread(target=servidor_zeromq, daemon=True).start()
    threading.Thread(target=servidor_metricas, daemon=True).start()
    try:
        threading.Thread(target=servidor_mqtt, daemon=True).start()
    except Exception as e:
        print(f"[MQTT] Error: {e}")

    print(f"  Panel: http://localhost:{PUERTO_WEB}")
    print("=" * 60)
    app.run(host='0.0.0.0', port=PUERTO_WEB, debug=False, threaded=True)
