import pandas as pd
import numpy as np
import time
import os
from scapy.all import sniff, IP, TCP, UDP
from tensorflow.keras.models import load_model
from prometheus_client import start_http_server, Counter, Gauge
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import joblib
import warnings

# --- Configuración de Conexiones ---
INFLUXDB_URL = os.getenv('INFLUXDB_URL', 'http://influxdb:8086')
INFLUXDB_TOKEN = os.getenv('INFLUXDB_TOKEN', 'my-super-secret-token')
INFLUXDB_ORG = os.getenv('INFLUXDB_ORG', 'my-org')
INFLUXDB_BUCKET = os.getenv('INFLUXDB_BUCKET', 'network_traffic')

# --- Carga del Modelo y Scaler ---
try:
    # Ignorar las advertencias de versión de scikit-learn
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        modelo = load_model('tu_modelo_lstm.h5', compile=False)
        scaler = joblib.load('mi_scaler.joblib')
    
    print("[*] Modelo de Deep Learning 'tu_modelo_lstm.h5' cargado exitosamente.")
    print("[*] Scaler 'mi_scaler.joblib' cargado exitosamente.")
except Exception as e:
    print(f"[!] Error crítico al cargar modelo o scaler: {e}")
    exit()

# --- Conexión a InfluxDB ---
try:
    # Como el capturador usa network_mode: host, debe conectar a localhost
    influx_client = InfluxDBClient(url="http://localhost:8086", token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
    write_api = influx_client.write_api(write_options=SYNCHRONOUS)
    print(f"[*] Conectado a InfluxDB en http://localhost:8086.")
except Exception as e:
    print(f"[!] Error al conectar con InfluxDB: {e}")
    exit()

# --- Métricas de Prometheus ---
PAQUETES_PROCESADOS = Counter('paquetes_de_red_procesados_total', 'Número total de paquetes procesados', ['protocolo'])
ANOMALIA_SCORE = Gauge('anomalia_de_red_score', 'Score de anomalía actual del último paquete analizado')
ANOMALIA_DETECTADA = Gauge('anomalia_de_red_detectada', 'Se establece en 1 si se detecta una anomalía (score > umbral)')
UMBRAL_ANOMALIA = 0.9 # Este umbral ahora es sobre el error de reconstrucción

def extraer_caracteristicas(paquete):
    """
    Extrae un conjunto rico de características numéricas del paquete.
    Garantiza que todas las claves esperadas siempre estén presentes.
    """
    if IP not in paquete:
        return None

    # Inicializa todas las características posibles con valores por defecto (0)
    features = {
        'ttl': paquete[IP].ttl,
        'length': len(paquete),
        'src_port': 0, 'dst_port': 0,
        'flag_fin': 0, 'flag_syn': 0, 'flag_rst': 0,
        'flag_psh': 0, 'flag_ack': 0, 'flag_urg': 0
    }
    
    # Sobrescribe los valores si el paquete es TCP
    if TCP in paquete:
        features['src_port'] = paquete[TCP].sport
        features['dst_port'] = paquete[TCP].dport
        flags = paquete[TCP].flags
        if 'F' in flags: features['flag_fin'] = 1
        if 'S' in flags: features['flag_syn'] = 1
        if 'R' in flags: features['flag_rst'] = 1
        if 'P' in flags: features['flag_psh'] = 1
        if 'A' in flags: features['flag_ack'] = 1
        if 'U' in flags: features['flag_urg'] = 1
    
    # Sobrescribe los valores si el paquete es UDP
    elif UDP in paquete:
        features['src_port'] = paquete[UDP].sport
        features['dst_port'] = paquete[UDP].dport

    # Añade las características no numéricas al final
    features['src_ip'] = paquete[IP].src
    features['dst_ip'] = paquete[IP].dst
    features['protocol'] = paquete[IP].proto
    
    return features

def preprocesar_paquete(features_df):
    """
    Preprocesa los datos en vivo utilizando el scaler cargado.
    """
    cols_numericas = ['ttl', 'length', 'src_port', 'dst_port', 'flag_fin', 'flag_syn', 'flag_rst', 'flag_psh', 'flag_ack', 'flag_urg']
    # Aseguramos el orden de las columnas para el scaler
    datos_numericos = features_df[cols_numericas].fillna(0)
    datos_escalados = scaler.transform(datos_numericos)
    datos_listos = np.reshape(datos_escalados, (datos_escalados.shape[0], 1, datos_escalados.shape[1]))
    return datos_listos

def packet_handler(paquete):
    """
    Función callback para cada paquete capturado.
    """
    features = extraer_caracteristicas(paquete)
    if features:
        try:
            df = pd.DataFrame([features])
            datos_preprocesados = preprocesar_paquete(df)

            # --- ¡AQUÍ ESTÁ LA CORRECCIÓN! ---
            # 1. Realizar la predicción (el autoencoder reconstruye la entrada)
            prediccion = modelo.predict(datos_preprocesados, verbose=0)
            
            # 2. El "score de anomalía" es el error de reconstrucción (MAE)
            #    Comparamos el original (datos_preprocesados) con la reconstrucción (prediccion)
            score_anomalia = np.mean(np.abs(prediccion - datos_preprocesados))
            # score_anomalia ahora es un solo número (scalar)

            es_anomalia = score_anomalia > UMBRAL_ANOMALIA

            protocolo_str = str(features.get('protocol', 'unknown'))
            PAQUETES_PROCESADOS.labels(protocolo=protocolo_str).inc()
            ANOMALIA_SCORE.set(float(score_anomalia))
            ANOMALIA_DETECTADA.set(1 if es_anomalia else 0)

            if es_anomalia:
                print(f"🚨 Anomalía Detectada! Score: {score_anomalia:.4f} | Paquete: {paquete.summary()}")
            
            point = Point("network_flow").tag("src_ip", features.get('src_ip')).tag("dst_ip", features.get('dst_ip')).tag("protocol", protocolo_str).field("score_anomalia", float(score_anomalia)).field("es_anomalia", int(es_anomalia))
            for key, value in features.items():
                if isinstance(value, (int, float)):
                    point = point.field(key, value)
            write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)
        except Exception as e:
            # Imprime el error real para una mejor depuración
            print(f"[!] Error procesando paquete: {type(e).__name__}: {e}")

def start_sniffing(interfaz='enp5s0'):
    print(f"[*] Iniciando sniffer de red en la interfaz {interfaz}...")
    # sniff(iface=interfaz, prn=packet_handler, store=0)
    # Dejamos que scapy encuentre la mejor interfaz por defecto
    sniff(prn=packet_handler, store=0)


if __name__ == '__main__':
    start_http_server(8000)
    print("[*] Servidor de Prometheus iniciado en http://localhost:8000")
    # Lo iniciamos sin interfaz específica para que Scapy elija la mejor
    # O puedes forzar la tuya: start_sniffing(interfaz='enp5s0')
    start_sniffing()

