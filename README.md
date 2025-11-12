# Sistema de Detección de Anomalías de Red (Prototipo PoC)

Este repositorio contiene el código de una **Prueba de Concepto (PoC)** para un sistema de detección de anomalías en tiempo real. El objetivo principal es validar la arquitectura y la integración de un stack tecnológico moderno (Docker, TIG Stack) para el procesamiento y visualización de datos de alta frecuencia.

---

## ⚠️ ¡Importante! Propósito de esta Prueba de Concepto

Este proyecto **NO** es un sistema de detección de intrusos listo para producción. Su propósito fue estrictamente técnico:

- **Validar las Herramientas**: Probar la viabilidad de usar Docker, Prometheus, InfluxDB y Grafana juntos.
- **Validar el Pipeline de Datos**: Asegurar que un script de Python puede capturar datos, procesarlos con un modelo de Keras y enviarlos a dos bases de datos (de métricas y de series temporales) en paralelo.
- **Probar el Despliegue**: Demostrar la facilidad de despliegue y replicación del entorno completo usando Docker Compose.

> **Nota**: El modelo de Deep Learning (`tu_modelo_lstm.h5`) es un placeholder entrenado con datos aleatorios (`generador_modelo_prueba.py`) solo para validar el flujo de inferencia.

---

## 🏛️ Arquitectura del Sistema (PoC)

El prototipo implementa un flujo de datos de doble vía para métricas en tiempo real y almacenamiento histórico.

1. **Captura**: Un contenedor `capturador` con Python y Scapy escucha el tráfico de red del host.
2. **Procesamiento**: Cada paquete es analizado, sus características son extraídas y preprocesadas (usando `mi_scaler.joblib`), y se calcula un score de anomalía (Error de Reconstrucción del Autoencoder) usando el modelo de Keras (`tu_modelo_lstm.h5`).
3. **Almacenamiento (Vía 1 - Tiempo Real)**: El script expone métricas instantáneas (ej. `anomalia_de_red_score`) en un endpoint (`:8000`). Prometheus recolecta (scrapes) estas métricas periódicamente.
4. **Almacenamiento (Vía 2 - Histórico)**: Los datos detallados de cada paquete (IPs, puertos, score) se escriben en InfluxDB para análisis a largo plazo.
5. **Visualización**: Grafana se conecta a ambas fuentes de datos (Prometheus y InfluxDB) para mostrarlas en un dashboard unificado.

---

## 🚀 Stack Tecnológico

### Orquestación
- **Docker** & **Docker Compose**

### Captura y Modelo (Servicio `capturador`)
- **Python 3.12**
- **Scapy**: Para la captura de paquetes de red
- **TensorFlow / Keras**: Para cargar y ejecutar el modelo de inferencia
- **Scikit-Learn**: Para cargar el scaler de preprocesamiento
- **Pandas / Numpy**: Para la manipulación de datos

### Base de Datos
- **InfluxDB 2.x**: Series temporales

### Monitoreo y Métricas
- **Prometheus**

### Visualización
- **Grafana**

---

## 🔧 Guía de Despliegue Rápido

El uso de Docker Compose hace que el despliegue en una nueva máquina sea trivial, siempre que los archivos del modelo ya existan.

### Prerrequisitos

- Docker
- Docker Compose (Versión 2, el comando es `docker compose`)
- Sistema operativo Linux (para `network_mode: "host"`)

### 1. Generar el Modelo de Prueba (Paso único)

Si no tienes los archivos `tu_modelo_lstm.h5` y `mi_scaler.joblib`, debes generarlos primero:

```bash
# 1. Crear y activar un entorno virtual
python3 -m venv venv
source venv/bin/activate

# 2. Instalar dependencias locales
pip install -r requirements.txt

# 3. Ejecutar el script generador
python generador_modelo_prueba.py

# 4. Desactivar el entorno (opcional)
deactivate
```

### 2. Levantar el Stack Completo

Con todos los archivos del proyecto en el directorio (incluyendo el `.h5` y `.joblib`), ejecuta:

```bash
# Construye las imágenes y levanta los contenedores
# -d (detached) los ejecuta en segundo plano
sudo docker compose up --build -d
```

### 3. Verificar el Estado

Para asegurarte de que todos los servicios están corriendo:

```bash
sudo docker compose ps
```

Deberías ver los 4 contenedores (`capturador`, `grafana`, `influxdb`, `prometheus`) con el estado **Up**.

---

## 🖥️ Acceso a los Servicios

Una vez levantado el stack, puedes acceder a las interfaces web desde la máquina host:

### Grafana (Visualización)
- **URL**: http://localhost:3000
- **User**: `admin`
- **Pass**: `admin` (te pedirá cambiarla)

### Prometheus (Métricas)
- **URL**: http://localhost:9090
- Para ver el estado del capturador: **Status → Targets**

### InfluxDB (Base de Datos)
- **URL**: http://localhost:8086
- **User**: `my-user`
- **Pass**: `my-super-password`

---

## 🚢 Despliegue en Otra Máquina

Una de las **mayores ventajas** de usar Docker y Docker Compose es la facilidad para replicar el entorno completo en cualquier máquina. Ya no necesitas instalar Python, TensorFlow, pip ni crear entornos virtuales en la nueva máquina. Toda la complejidad está empaquetada en los archivos de configuración.

### Prerrequisitos en la Nueva Máquina

En la máquina de destino, **solo necesitas instalar Docker y Docker Compose**. No se requiere Python, pip, venv, TensorFlow ni ninguna de las librerías de `requirements.txt`.

#### Instalación en Ubuntu/Debian:

```bash
# 1. Actualizar e instalar prerrequisitos
sudo apt-get update
sudo apt-get install ca-certificates curl

# 2. Añadir la clave GPG oficial de Docker
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# 3. Añadir el repositorio de Docker
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update

# 4. Instalar Docker Engine y el plugin de Compose
sudo apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 5. (MUY RECOMENDADO) Añadir tu usuario al grupo docker
sudo usermod -aG docker $USER
```

> **Importante**: Después del paso 5, cierra sesión y vuelve a iniciarla para que los permisos de Docker se apliquen correctamente.

### Pasos para el Despliegue

#### 1. Transferir los Archivos del Proyecto

Necesitas copiar la carpeta del proyecto a la nueva máquina. **No incluyas la carpeta `venv`** (el archivo `.dockerignore` debería excluirla automáticamente).

**Método A: Usando Git (Recomendado)**

```bash
# En la nueva máquina
git clone https://github.com/tu-usuario/tu-proyecto.git
cd tu-proyecto
```

**Método B: Comprimir y Copiar**

En tu máquina actual:
```bash
# Ve a la carpeta padre de tu proyecto
cd ~/
# Crea un archivo .zip (excluyendo venv)
zip -r RESIDENCIAS.zip RESIDENCIAS -x "RESIDENCIAS/venv/*"
```

Transfiere `RESIDENCIAS.zip` a la nueva máquina y descomprímelo:
```bash
unzip RESIDENCIAS.zip
cd RESIDENCIAS
```

**Archivos esenciales que deben estar presentes:**
- `docker-compose.yml`
- `Dockerfile`
- `capturador.py`
- `requirements.txt`
- `prometheus.yml`
- `tu_modelo_lstm.h5`
- `mi_scaler.joblib`
- `.dockerignore`

#### 2. Levantar el Sistema

Dentro de la carpeta del proyecto en la nueva máquina:

```bash
sudo docker compose up --build -d
```

- `--build`: Construye la imagen del contenedor (importante en la primera ejecución)
- `-d`: Ejecuta en modo detached (segundo plano), permitiendo cerrar la terminal

#### 3. Verificar el Estado

```bash
sudo docker compose ps
```

Deberías ver los 4 contenedores con estado **Up**.

#### 4. Acceder a los Servicios

Usa la dirección IP de la nueva máquina en lugar de `localhost`:

- **Grafana**: `http://<IP_DEL_SERVIDOR>:3000`
- **Prometheus**: `http://<IP_DEL_SERVIDOR>:9090`
- **InfluxDB**: `http://<IP_DEL_SERVIDOR>:8086`

### ⚠️ Consideración Importante: Interfaz de Red

El script `capturador.py` está configurado para capturar tráfico de red. La nueva máquina podría tener un nombre de interfaz diferente (ej. `eth0`, `ens33`, en lugar de `enp5s0`).

**Solución Recomendada**: Asegúrate de que `capturador.py` no especifique ninguna interfaz:

```python
if __name__ == '__main__':
    start_http_server(8000)
    print("[*] Servidor de Prometheus iniciado en http://localhost:8000")
    start_sniffing()  # Sin interfaz especificada - portabilidad automática
```

Cuando Scapy se ejecuta sin especificar interfaz, detecta automáticamente la ruta por defecto.

**Solución Manual** (si es necesario):
1. Ejecuta `ip a` en la nueva máquina para identificar la interfaz principal
2. Edita `capturador.py` y especifica la interfaz en `start_sniffing()`
3. Ejecuta `sudo docker compose up --build -d` para aplicar los cambios

---

## 🔮 Próximos Pasos (Visión del Proyecto Final)

Este prototipo validó la arquitectura. El proyecto final evolucionará de la siguiente manera:

- **Fuente de Datos**: Se reemplazará Scapy por un sistema de ingesta de logs de servidor web (ej. Nginx, Apache).
- **Modelo Especializado**: Se entrenará un nuevo modelo con un dataset especializado en la detección de patrones de ataque en logs web (ej. Inyección SQL, XSS, Scaneo de directorios).
- **Despliegue**: La arquitectura de Docker Compose se desplegará en un servidor de producción para monitorear el servidor web en vivo.

---

## 📄 Licencia

Instituto Tecnologico de Morelia

