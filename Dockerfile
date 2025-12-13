# Usa uma imagem Python leve mas compatível
FROM python:3.10-slim

# 1. Instalação de Dependências de Sistema (GDAL/C++)
# Essencial para GeoPandas funcionar sem erros de compilação
RUN apt-get update && apt-get install -y \
    build-essential \
    gdal-bin \
    libgdal-dev \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 2. Configuração de Variáveis de Ambiente para o Compilador
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

# Define diretório de trabalho
WORKDIR /app

# Copia os ficheiros do projeto
COPY . .

# 3. Instalação Inteligente do GDAL (Python)
# Verifica a versão do GDAL do sistema e instala a versão Python correspondente
RUN pip install --no-cache-dir "GDAL==$(gdal-config --version)"

# 4. Instalação das restantes dependências
RUN pip install --no-cache-dir -r requirements.txt

# Expõe a porta (documental)
EXPOSE 8501

# 5. COMANDO DE ARRANQUE (A CORREÇÃO DO 502)
# Usa a variável $PORT fornecida pelo Railway/Render.
CMD sh -c 'streamlit run app.py --server.port=${PORT:-8501} --server.address=0.0.0.0'
