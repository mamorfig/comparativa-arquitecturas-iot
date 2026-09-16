# main.py - ESP32-S3 TFM Comparativa de Arquitecturas IoT
# WiFi OFF entre fotos para máxima estabilidad
# Doble WiFi: huerta + casa (intenta una, si falla usa la otra)
# ZeroMQ vs MQTT vs RabbitMQ + Telegram
# MQTT SIMPLIFICADO (publicar sin esperar)
# Configuración huerta: ae_level=2, brightness=-1, contrast=2
# Notificaciones Telegram al cambiar día/noche y cuando servidor caído
# Zona horaria automática por IP-API
# UXGA 1600×1200 | JPEG Q90

import network
import socket
import time
import gc
import ssl
import ntptime
import urequests
import ujson
from machine import WDT, reset, RTC
from camera import Camera, FrameSize, PixelFormat
from umqtt.simple import MQTTClient

# ============ CONFIGURACIÓN ============
# WiFi de la huerta (principal)
SSID_HUERTA = "Wi-Fi XXXXXX"
PASSWORD_HUERTA = "XXXXXXXXXX"

# WiFi de casa (secundario)
SSID_CASA = "vodafoneXXXXXXX"
PASSWORD_CASA = "XXXXXXXXXXXXXX"

SERVER_IP = "111.111.111.11"

ZEROMQ_PORT = 9999
MQTT_PORT = 1883
RABBITMQ_PORT = 5002
METRICAS_PORT = 9998
MQTT_TOPIC_ENVIO = "cultivo/foto"

TELEGRAM_TOKEN = "111111111111:XXXXXXXXXXXXXXXXXXX"
CHAT_ID = "1111111111111111"

INTERVALO_FOTOS = 300
FRAME_SIZE = FrameSize.UXGA
FRAME_SIZE_TELEGRAM = FrameSize.QQVGA
PIXEL_FORMAT = PixelFormat.JPEG
JPEG_QUALITY = 90
JPEG_QUALITY_TELEGRAM = 15
UMBRAL_NOCHE = 600

ARQ_ZEROMQ = "ZeroMQ"
ARQ_MQTT = "MQTT"
ARQ_RABBITMQ = "RabbitMQ"
ARQ_TELEGRAM = "Telegram"

wdt = WDT(timeout=600000)
ultimos_tamanos = []
hora_sincronizada = False
ultimo_modo = None
fallos_servidor = 0
zona_horaria = "UTC"

# ============ FUNCIONES AUXILIARES ============
def log(mensaje):
    _, _, _, h, m, s, _, _ = time.localtime()
    print(f"[{h:02d}:{m:02d}:{s:02d}] {mensaje}")

def es_de_dia_local():
    _, _, _, hora, _, _, _, _ = time.localtime()
    return 7 <= hora < 21  # Día: 7:00-20:59 hora local

# ============ OBTENER ZONA HORARIA POR IP ============
def obtener_offset_utc():
    global zona_horaria
    try:
        resp = urequests.get("http://ip-api.com/json/?fields=timezone,offset")
        if resp.text and resp.text.startswith('{'):
            datos = ujson.loads(resp.text)
            resp.close()
            offset_segundos = int(datos.get('offset', 7200))
            offset_horas = offset_segundos // 3600
            zona_horaria = datos.get('timezone', 'UTC')
            log(f"🌍 Zona horaria: {zona_horaria} (UTC{offset_horas:+d})")
            return offset_horas
    except:
        pass
    zona_horaria = "Europe/Madrid"
    return 2  # Default España verano

# ============ ENVIAR MENSAJE DE TEXTO A TELEGRAM ============
def enviar_mensaje_telegram(texto):
    try:
        ai = socket.getaddrinfo("api.telegram.org", 443)
        addr = ai[0][-1]
        sock = socket.socket()
        sock.settimeout(15)
        sock.connect(addr)
        ssl_sock = ssl.wrap_socket(sock, server_hostname="api.telegram.org")
        
        body = f'chat_id={CHAT_ID}&text={texto}'.encode()
        
        request = (
            f"POST /bot{TELEGRAM_TOKEN}/sendMessage HTTP/1.1\r\n"
            f"Host: api.telegram.org\r\n"
            f"Content-Type: application/x-www-form-urlencoded\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode() + body
        
        ssl_sock.send(request)
        ssl_sock.recv(512)
        ssl_sock.close()
        log(f"📱 Telegram: {texto}")
    except Exception as e:
        log(f"📱 Telegram ⚠️ {e}")

# ============ WIFI (doble red) ============
def conectar_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(False)
    time.sleep(1)
    wlan.active(True)
    time.sleep(1)
    if wlan.isconnected():
        return wlan
    
    redes = [
        (SSID_HUERTA, PASSWORD_HUERTA),
        (SSID_CASA, PASSWORD_CASA),
    ]
    
    for ssid, password in redes:
        log(f"📶 Intentando: {ssid}")
        wlan.connect(ssid, password)
        for _ in range(15):
            if wlan.isconnected():
                log(f"📶 WiFi ✅ {wlan.ifconfig()[0]} ({ssid})")
                return wlan
            time.sleep(1)
            wdt.feed()
        
        if not wlan.isconnected():
            log(f"⚠️ {ssid} no disponible")
            wlan.active(False)
            time.sleep(1)
            wlan.active(True)
            time.sleep(1)
    
    log("🔄 Reintentando...")
    wlan.connect(SSID_HUERTA, PASSWORD_HUERTA)
    for _ in range(60):
        if wlan.isconnected():
            return wlan
        time.sleep(1)
        wdt.feed()
    
    time.sleep(2)
    reset()

def desconectar_wifi(wlan):
    log("📴 WiFi OFF")
    wlan.active(False)
    time.sleep(0.5)

# ============ SINCRONIZAR HORA POR NTP + IP ============
def sincronizar_hora():
    global hora_sincronizada
    if not hora_sincronizada:
        try:
            ntptime.settime()
            
            # Obtener offset automático por IP
            offset = obtener_offset_utc()
            
            rtc = RTC()
            año, mes, dia, dia_semana, hora_utc, minuto, segundo, microseg = rtc.datetime()
            hora_local = (hora_utc + offset) % 24
            rtc.datetime((año, mes, dia, dia_semana, hora_local, minuto, segundo, microseg))
            
            hora_sincronizada = True
            _, _, _, h, m, _, _, _ = time.localtime()
            log(f"🕐 Hora {zona_horaria}: {h:02d}:{m:02d}")
        except Exception as e:
            log(f"⚠️ Error NTP: {e}")

# ============ CALIDAD ============
def configurar_calidad_base(cam):
    cam.bpc = True; cam.wpc = True; cam.lenc = True
    cam.dcw = True; cam.raw_gma = True
    cam.whitebal = True; cam.awb_gain = True

def ajustar_camara(cam, luz_anterior):
    configurar_calidad_base(cam)
    if luz_anterior is None:
        cam.aec2 = False; cam.agc_gain = 0; cam.gainceiling = 0
        cam.brightness = -1; cam.ae_level = 2; cam.saturation = 1
        cam.contrast = 2; cam.gain_ctrl = True; cam.aec_value = 200
    elif luz_anterior > UMBRAL_NOCHE:
        cam.aec2 = True; cam.agc_gain = 25; cam.gainceiling = 5
        cam.brightness = 2; cam.ae_level = 0; cam.saturation = 0
        cam.contrast = 1; cam.gain_ctrl = False
    else:
        cam.aec2 = False; cam.agc_gain = 0; cam.gainceiling = 0
        cam.brightness = -1; cam.ae_level = 2; cam.saturation = 1
        cam.contrast = 2; cam.gain_ctrl = True; cam.aec_value = 200

# ============ CAPTURA SEGURA ============
def capturar_imagen_segura(cam, max_intentos=3):
    for intento in range(max_intentos):
        try:
            img = cam.capture()
            if img is None:
                log(f"⚠️ Captura None, reintento {intento+1}")
                time.sleep(1)
                continue
            size = len(img)
            if size < 1000:
                log(f"⚠️ Imagen pequeña ({size}B), reintento {intento+1}")
                del img
                gc.collect()
                time.sleep(1)
                continue
            return img
        except Exception as e:
            log(f"⚠️ Error captura: {e}, reintento {intento+1}")
            time.sleep(2)
    return None

# ============ ENVIAR LATENCIA ============
def enviar_latencia(arq, num_foto, latencia):
    try:
        sock = socket.socket()
        sock.settimeout(5)
        sock.connect((SERVER_IP, METRICAS_PORT))
        msg = f"{arq}|{num_foto}|{latencia}".encode()
        sock.send(msg)
        sock.close()
    except:
        pass

# ============ ENVIAR A TELEGRAM ============
def enviar_telegram(img_bytes, num_foto, modo):
    try:
        ai = socket.getaddrinfo("api.telegram.org", 443)
        addr = ai[0][-1]
        sock = socket.socket()
        sock.settimeout(15)
        sock.connect(addr)
        ssl_sock = ssl.wrap_socket(sock, server_hostname="api.telegram.org")
        
        boundary = "ESP32Boundary"
        caption = f"{modo} #{num_foto} | Telegram"
        body = b'--' + boundary.encode() + b'\r\n'
        body += b'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
        body += CHAT_ID.encode() + b'\r\n'
        body += b'--' + boundary.encode() + b'\r\n'
        body += b'Content-Disposition: form-data; name="caption"\r\n\r\n'
        body += caption.encode() + b'\r\n'
        body += b'--' + boundary.encode() + b'\r\n'
        body += b'Content-Disposition: form-data; name="photo"; filename="foto.jpg"\r\n'
        body += b'Content-Type: image/jpeg\r\n\r\n'
        body += img_bytes + b'\r\n'
        body += b'--' + boundary.encode() + b'--\r\n'
        
        request = (
            f"POST /bot{TELEGRAM_TOKEN}/sendPhoto HTTP/1.1\r\n"
            f"Host: api.telegram.org\r\n"
            f"Content-Type: multipart/form-data; boundary={boundary}\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode() + body
        
        t0 = time.ticks_ms()
        ssl_sock.send(request)
        ssl_sock.recv(512)
        t1 = time.ticks_ms()
        ssl_sock.close()
        
        latencia = time.ticks_diff(t1, t0)
        log(f"📱 Telegram OK | {len(img_bytes)}B | {latencia}ms")
        enviar_latencia(ARQ_TELEGRAM, num_foto, latencia)
    except Exception as e:
        log(f"📱 Telegram ⚠️ {e}")

# ============ ZeroMQ ============
def enviar_zeromq(img_bytes):
    for intento in range(3):
        try:
            sock = socket.socket()
            sock.settimeout(30)
            t0 = time.ticks_ms()
            sock.connect((SERVER_IP, ZEROMQ_PORT))
            sock.send(len(img_bytes).to_bytes(4, 'big'))
            for i in range(0, len(img_bytes), 4096):
                sock.send(img_bytes[i:i+4096])
            sock.recv(4)
            t1 = time.ticks_ms()
            sock.close()
            return True, time.ticks_diff(t1, t0)
        except Exception as e:
            log(f"ZeroMQ ⚠️ {intento+1}/3: {e}")
            try: sock.close()
            except: pass
            if intento < 2: time.sleep(5)
    return False, 0

# ============ MQTT SIMPLIFICADO ============
def enviar_mqtt(img_bytes):
    for intento in range(3):
        try:
            client = MQTTClient("esp32_tfm", SERVER_IP, port=MQTT_PORT)
            client.connect()
            t0 = time.ticks_ms()
            client.publish(MQTT_TOPIC_ENVIO, img_bytes)
            t1 = time.ticks_ms()
            client.disconnect()
            return True, time.ticks_diff(t1, t0)
        except Exception as e:
            log(f"MQTT ⚠️ {intento+1}/3: {e}")
            try: client.disconnect()
            except: pass
            if intento < 2: time.sleep(5)
    return False, 0

# ============ RabbitMQ ============
def enviar_rabbitmq(img_bytes):
    global ultimos_tamanos
    if len(ultimos_tamanos) > 0:
        tamano_padding = sum(ultimos_tamanos) // len(ultimos_tamanos)
    else:
        tamano_padding = len(img_bytes)
    for intento in range(3):
        try:
            sock = socket.socket()
            sock.settimeout(30)
            t0 = time.ticks_ms()
            sock.connect((SERVER_IP, RABBITMQ_PORT))
            padding = 'X' * tamano_padding
            body = (b'{"arquitectura":"RabbitMQ","size":' + 
                    str(tamano_padding).encode() + 
                    b',"padding":"' + padding.encode() + b'"}')
            header = (
                f"POST /api/foto HTTP/1.1\r\n"
                f"Host: {SERVER_IP}:{RABBITMQ_PORT}\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                f"Connection: close\r\n"
                f"\r\n"
            ).encode()
            sock.send(header + body)
            respuesta = sock.recv(1024)
            t1 = time.ticks_ms()
            sock.close()
            if b'200' in respuesta or b'OK' in respuesta:
                return True, time.ticks_diff(t1, t0)
            else:
                log(f"RabbitMQ ⚠️ {respuesta[:80]}")
                return False, 0
        except Exception as e:
            log(f"RabbitMQ ⚠️ {intento+1}/3: {e}")
            try: sock.close()
            except: pass
            if intento < 2: time.sleep(5)
    return False, 0

# ============ ENVIAR ============
def enviar_foto_rotativo(img_bytes, arq, num_foto):
    log(f"📤 #{num_foto} | {arq} | {len(img_bytes)}B...")
    if arq == ARQ_ZEROMQ: return enviar_zeromq(img_bytes)
    elif arq == ARQ_MQTT: return enviar_mqtt(img_bytes)
    elif arq == ARQ_RABBITMQ: return enviar_rabbitmq(img_bytes)
    return False, 0

# ============ CÁMARA ============
def crear_camara(frame_size=FRAME_SIZE, jpeg_quality=JPEG_QUALITY):
    for intento in range(3):
        try:
            cam = Camera(frame_size=frame_size, pixel_format=PIXEL_FORMAT,
                         jpeg_quality=jpeg_quality, fb_count=1, init=True)
            cam.hmirror = True; cam.vflip = True
            cam.exposure_ctrl = True
            time.sleep(1)
            return cam
        except Exception as e:
            log(f"[Cam] ⚠️ {intento+1}: {e}")
            time.sleep(3)
    reset()

# ============ PROGRAMA PRINCIPAL ============
print("\n" + "=" * 60)
print("🎓 TFM - COMPARATIVA ARQUITECTURAS IoT")
print(f"   📷 UXGA 1600×1200 | Q{JPEG_QUALITY}")
print(f"   🔄 ZeroMQ → MQTT → RabbitMQ")
print(f"   📱 + Telegram (notificaciones)")
print(f"   📡 Doble WiFi (huerta + casa)")
print(f"   🌻 Huerta: ae=2, bright=-1, contrast=2")
print(f"   🛡️ Captura segura anti-bloqueo")
print(f"   🕐 Hora NTP + zona horaria automática")
print(f"   ☀️ Solo fotos de día (7:00-21:00)")
print(f"   🌙 Noche: ESP32 despierto")
print(f"   📱 Aviso si servidor caído")
print("=" * 60)

errores = 0
luz_anterior = None
foto_num = 0
arquitecturas = [ARQ_ZEROMQ, ARQ_MQTT, ARQ_RABBITMQ]

log(f"⏱ Cada {INTERVALO_FOTOS}s | WiFi OFF entre fotos")

while True:
    try:
        # ===== SINCRONIZAR HORA (primera vez) + FOTO INICIAL =====
        if not hora_sincronizada:
            wlan_temp = conectar_wifi()
            sincronizar_hora()
            desconectar_wifi(wlan_temp)
            del wlan_temp
            gc.collect()
            
            if es_de_dia_local():
                log("📷 Primera foto inicial...")
                wlan = conectar_wifi()
                cam = crear_camara(FRAME_SIZE, JPEG_QUALITY)
                ajustar_camara(cam, None)
                img = capturar_imagen_segura(cam)
                if img:
                    foto_num = 1
                    arq = arquitecturas[0]
                    size = len(img)
                    exito, latencia = enviar_foto_rotativo(img, arq, foto_num)
                    if exito:
                        enviar_latencia(arq, foto_num, latencia)
                        log(f"✅ {arq} #{foto_num}: {size}B | RTT={latencia}ms")
                    else:
                        fallos_servidor = 1
                    del img
                try: cam.deinit()
                except: pass
                del cam; gc.collect()
                
                cam_tg = crear_camara(FRAME_SIZE_TELEGRAM, JPEG_QUALITY_TELEGRAM)
                img_tg = capturar_imagen_segura(cam_tg)
                if img_tg:
                    enviar_telegram(bytes(img_tg), foto_num, "☀️")
                try: cam_tg.deinit()
                except: pass
                del cam_tg, img_tg; gc.collect()
                
                desconectar_wifi(wlan)
                del wlan; gc.collect()
        
        # ===== DETECTAR CAMBIO DÍA/NOCHE =====
        dia_actual = es_de_dia_local()
        if dia_actual != ultimo_modo:
            if dia_actual:
                wlan_notif = conectar_wifi()
                enviar_mensaje_telegram("☀️ El dispositivo ha entrado en modo DÍA. Comenzando a tomar fotos.")
                desconectar_wifi(wlan_notif)
                del wlan_notif
                gc.collect()
            else:
                wlan_notif = conectar_wifi()
                enviar_mensaje_telegram("🌙 El dispositivo ha entrado en modo NOCHE. Dejando de tomar fotos para ahorrar batería.")
                desconectar_wifi(wlan_notif)
                del wlan_notif
                gc.collect()
            ultimo_modo = dia_actual
        
        # ===== MODO NOCHE / DÍA =====
        if dia_actual:
            # MODO DÍA
            foto_num += 1
            arq = arquitecturas[(foto_num - 1) % 3]
            
            wlan = conectar_wifi()
            
            log("📷 Cámara UXGA ON")
            cam = crear_camara(FRAME_SIZE, JPEG_QUALITY)
            ajustar_camara(cam, luz_anterior)
            
            img = capturar_imagen_segura(cam)
            
            if img is None:
                log("❌ No se pudo capturar UXGA")
                errores += 1
                try: cam.deinit()
                except: pass
                del cam; cam = None; gc.collect()
                desconectar_wifi(wlan)
                continue
            
            size = len(img)
            luz_actual = cam.aec_value
            luz_anterior = luz_actual
            
            if arq in [ARQ_ZEROMQ, ARQ_MQTT]:
                ultimos_tamanos.append(size)
                if len(ultimos_tamanos) > 10:
                    ultimos_tamanos.pop(0)
            
            exito, latencia = enviar_foto_rotativo(img, arq, foto_num)
            del img; gc.collect()
            
            modo = "🌙" if luz_actual > UMBRAL_NOCHE else "☀️"
            
            if exito:
                errores = 0
                fallos_servidor = 0
                log(f"✅ {arq} #{foto_num}: {size}B | RTT={latencia}ms | {modo}")
                enviar_latencia(arq, foto_num, latencia)
            else:
                errores += 1
                fallos_servidor += 1
                log(f"❌ {arq} #{foto_num}: FALLÓ")
            
            log("📷 Cámara OFF")
            try: cam.deinit()
            except: pass
            del cam; cam = None; gc.collect()
            
            # Telegram
            log("📷 Cámara QQVGA ON (Telegram)")
            cam_tg = crear_camara(FRAME_SIZE_TELEGRAM, JPEG_QUALITY_TELEGRAM)
            img_tg = capturar_imagen_segura(cam_tg)
            if img_tg:
                img_tg_bytes = bytes(img_tg)
                enviar_telegram(img_tg_bytes, foto_num, modo)
                del img_tg_bytes
            try: cam_tg.deinit()
            except: pass
            del cam_tg, img_tg; cam_tg = None; gc.collect()
            
            # Si las 3 arquitecturas fallaron, avisar por Telegram
            if fallos_servidor >= 3:
                enviar_mensaje_telegram("⚠️ Servidor no accesible. No se pudo enviar imágenes al servidor.")
                fallos_servidor = 0
            
            # APAGAR WiFi
            desconectar_wifi(wlan)
            del wlan; wlan = None
            gc.collect()
            
            log(f"✅ OK | {foto_num} fotos | RAM: {gc.mem_free()/1024:.0f} KB | Esperando...")
            
            if errores >= 5:
                time.sleep(2); reset()
            
            for _ in range(INTERVALO_FOTOS):
                time.sleep(1)
                wdt.feed()
        else:
            # MODO NOCHE
            log("🌙 Noche. Esperando...")
            for _ in range(600):
                time.sleep(1)
                wdt.feed()
        
    except MemoryError:
        time.sleep(2); reset()
    except Exception as e:
        log(f"💥 Error: {e}")
        errores += 1
        if errores >= 3: time.sleep(2); reset()
        time.sleep(30)
        wdt.feed()