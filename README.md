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
