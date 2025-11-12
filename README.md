# RESIDENCIAS-FER-PEDRO
## 1. Actualizar e instalar prerrequisitos
sudo apt-get update
sudo apt-get install ca-certificates curl

## 2. Añadir la clave GPG oficial de Docker
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

## 3. Añadir el repositorio de Docker
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update

## 4. Instalar Docker Engine y el plugin de Compose
sudo apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

## 5. (MUY RECOMENDADO) Añadir tu usuario al grupo docker
sudo usermod -aG docker $USER

# Levanta el Sistema
sudo docker compose up --build -d

# Verifica que Funciona
sudo docker compose ps

# Accede a los Servicios
Grafana: http://<IP_DEL_SERVIDOR>:3000
Prometheus: http://<IP_DEL_SERVIDOR>:9090
InfluxDB: http://<IP_DEL_SERVIDOR>:8086

# La Interfaz de Red
Hay una cosa que podría necesitar un pequeño ajuste.
Tu script capturador.py está configurado para escuchar el tráfico. En tus logs anteriores, vi que detectó la interfaz enp5s0.
