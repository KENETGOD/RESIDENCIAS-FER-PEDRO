import time
import pandas as pd
import numpy as np
import joblib
import os
import re
from collections import deque
from tensorflow.keras.models import load_model
from prometheus_client import start_http_server, Counter, Gauge
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import warnings

# --- CONFIGURACIÓN ---
# Ruta del log de Apache dentro del contenedor (mapeado en docker-compose.yml)
LOG_FILE_PATH = '/var/log/apache2/access.log'
INFLUXDB_URL = os.getenv('INFLUXDB_URL', 'http://localhost:8086')
INFLUXDB_TOKEN = os.getenv('INFLUXDB_TOKEN', 'my-super-secret-token')
INFLUXDB_ORG = os.getenv('INFLUXDB_ORG', 'my-org')
INFLUXDB_BUCKET = os.getenv('INFLUXDB_BUCKET', 'network_traffic')

# IMPORTANTE: Debe ser igual al usado en el entrenamiento
TIMESTEPS = 10 

# --- CARGA DE ARTEFACTOS (Nombres Corregidos) ---
print("[*] Cargando modelo y transformadores...")
try:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        # Aquí están los nombres actualizados que me diste
        modelo = load_model('modelo_logs_1.h5', compile=False)
        scaler = joblib.load('scaler_logs_1.joblib')
        encoders = joblib.load('encoders_logs_1.joblib')
    print("[*] Artefactos cargados exitosamente.")
except Exception as e:
    print(f"[!] Error crítico cargando archivos: {e}")
    # exit() # Descomentar en producción

# --- CONEXIÓN INFLUXDB ---
try:
    influx_client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
    write_api = influx_client.write_api(write_options=SYNCHRONOUS)
except Exception as e:
    print(f"[!] Error conectando a InfluxDB: {e}")

# --- MÉTRICAS PROMETHEUS ---
PAQUETES_PROCESADOS = Counter('logs_procesados_total', 'Total de líneas de log analizadas')
ANOMALIA_SCORE = Gauge('log_anomalia_score', 'Score de anomalía del último log')
ANOMALIA_DETECTADA = Gauge('log_anomalia_detectada', '1 si es anomalía, 0 si no')
UMBRAL = 0.15 

# Buffer (Memoria a corto plazo para la secuencia LSTM)
ventana_deslizante = deque(maxlen=TIMESTEPS)

def safe_transform(encoder, value):
    """
    Maneja valores nuevos (ej. una IP nunca vista) asignándolos a una clase 'desconocida' (0)
    para que el sistema no falle en producción.
    """
    try:
        # Intentamos transformar el valor
        return encoder.transform([str(value)])[0]
    except ValueError:
        # Si el LabelEncoder no conoce el valor (ej. IP nueva), retornamos 0
        return 0 

def parse_apache_log(line):
    """
    Parsea logs de Apache Combined Format usando Regex.
    ESTA ES LA VERSIÓN CORRECTA QUE REEMPLAZA AL 'split()'.
    Maneja correctamente las fechas con espacios y User Agents complejos.
    """
    # Regex robusta para Apache Combined Log
    # Grupos: 1:IP, 2:Timestamp, 3:Method, 4:URL, 5:Protocol, 6:Status, 7:Size, 8:Referer, 9:UserAgent
    regex = r'^(\S+) \S+ \S+ \[(.*?)\] "(\S+) (\S+) (\S+)" (\d+) (\d+|-) "(.*?)" "(.*?)"'
    
    match = re.match(regex, line)
    if not match:
        return None
    
    data = match.groups()
    
    # Manejo del tamaño de respuesta (Apache usa '-' si es 0 bytes o redirección)
    size = data[6]
    if size == '-':
        size = 0
    else:
        size = int(size)

    return {
        'ip': data[0],
        'timestamp': data[1],
        'method': data[2],
        'url': data[3],
        'http_version': data[4],
        'status_code': int(data[5]),
        'response_size': size,
        'referer': data[7],
        'user_agent': data[8],
        # Campos placeholder para cumplir con el modelo entrenado
        # (Apache access.log por defecto no tiene TLS/Cipher)
        'tls_version': '-', 
        'cipher_suite': '-',
        'log_source': 'apache_access_log'
    }

def procesar_log(raw_line):
    parsed_data = parse_apache_log(raw_line)
    
    # Si la línea no es válida (ej. vacía o error de formato), saltar
    if not parsed_data: 
        return

    try:
        # 1. Codificar Categorías (Texto -> Números)
        encoded_data = []
        
        # IMPORTANTE: El orden debe ser IDÉNTICO al usado en el entrenamiento.
        # Basado en tu dataset: ip, method, url, http_version, status, size, referer, ua, tls, cipher, source
        
        features_dict = parsed_data # Copia para guardar en DB
        vector_fila = []

        # -- Procesar Columnas Categóricas --
        # Usamos safe_transform para evitar errores con datos nuevos
        cat_cols = ['ip', 'method', 'url', 'http_version', 'referer', 
                    'user_agent', 'tls_version', 'cipher_suite', 'log_source']
        
        for col in cat_cols:
            val = str(parsed_data.get(col, '-'))
            if col in encoders:
                val_encoded = safe_transform(encoders[col], val)
            else:
                val_encoded = 0
            vector_fila.append(val_encoded)

        # -- Procesar Columnas Numéricas --
        num_cols = ['status_code', 'response_size']
        for col in num_cols:
            val = parsed_data.get(col, 0)
            vector_fila.append(float(val))

        # 2. Escalar (Normalizar 0-1)
        vector_np = np.array([vector_fila])
        
        try:
            vector_scaled = scaler.transform(vector_np)
        except ValueError as ve:
            print(f"[!] Error de dimensiones en Scaler: {ve}")
            return

        # 3. Añadir a la ventana temporal
        ventana_deslizante.append(vector_scaled[0])

        # Solo predecimos cuando la ventana está llena (tenemos contexto suficiente)
        if len(ventana_deslizante) == TIMESTEPS:
            # Convertir a formato 3D para LSTM: (samples, timesteps, features)
            secuencia = np.array([list(ventana_deslizante)])
            
            # 4. Predicción (El modelo intenta reconstruir la entrada)
            reconstruccion = modelo.predict(secuencia, verbose=0)
            
            # 5. Calcular Error (MAE) -> Este es el Score de Anomalía
            mae = np.mean(np.abs(reconstruccion - secuencia))
            
            es_anomalia = mae > UMBRAL

            # 6. Métricas y Almacenamiento
            PAQUETES_PROCESADOS.inc()
            ANOMALIA_SCORE.set(mae)
            ANOMALIA_DETECTADA.set(1 if es_anomalia else 0)

            if es_anomalia:
                print(f"🚨 ANOMALÍA: IP={features_dict['ip']} URL={features_dict['url']} Score={mae:.4f}")
            
            # Enviar a InfluxDB
            p = Point("web_traffic") \
                .tag("ip", str(features_dict['ip'])) \
                .tag("method", str(features_dict['method'])) \
                .tag("status", str(features_dict['status_code'])) \
                .field("score_anomalia", float(mae)) \
                .field("is_anomaly", int(es_anomalia)) \
                .field("response_size", int(features_dict['response_size'])) \
                .field("url", str(features_dict['url']))
            
            write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=p)

    except Exception as e:
        print(f"[!] Error procesando log: {e}")

def tail_file(filepath):
    """
    Lee el archivo en modo 'tail -f'.
    """
    # Espera activa si el archivo no existe aún
    while not os.path.exists(filepath):
        print(f"[*] Esperando archivo {filepath}...")
        time.sleep(2)

    file = open(filepath, 'r')
    file.seek(0, 2) # Ir al final del archivo para leer solo nuevos logs
    print(f"[*] Escuchando logs de Apache en: {filepath}")
    
    while True:
        line = file.readline()
        if not line:
            time.sleep(0.1) # Breve pausa para no saturar CPU
            continue
        yield line

if __name__ == '__main__':
    start_http_server(8000)
    print("[*] Monitor de Logs Apache iniciado en puerto 8000.")
    
    # Iniciar bucle principal
    for line in tail_file(LOG_FILE_PATH):
        procesar_log(line)