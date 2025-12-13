# Usa uma imagem Python oficial leve
FROM python:3.10-slim

# Instala dependências do sistema necessárias para o GeoPandas/GDAL
# build-essential é adicionado para garantir que temos 'make', 'gcc', etc.
RUN apt-get update && apt-get install -y \
    build-essential \
    gdal-bin \
    libgdal-dev \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Configura variáveis de ambiente para o compilador achar o GDAL
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

# Define diretório de trabalho
WORKDIR /app

# Copia os arquivos do projeto
COPY . .

# --- CORREÇÃO DE BUILD ---
# Antes de rodar o requirements, instalamos o binding Python do GDAL
# exatamente na mesma versão da biblioteca de sistema instalada pelo apt.
# Isso evita erros de "header mismatch" ou falha de compilação.
RUN pip install --no-cache-dir "GDAL==$(gdal-config --version)"

# Instala as demais dependências
RUN pip install --no-cache-dir -r requirements.txt

# Expõe a porta padrão do Streamlit
EXPOSE 8501

# Comando para rodar o app
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
