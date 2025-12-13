# Usa uma imagem Python oficial leve
FROM python:3.10-slim

# Instala dependências do sistema necessárias para o GeoPandas/GDAL
# Isso é CRÍTICO. Sem isso, o app quebra na nuvem.
RUN apt-get update && apt-get install -y \
    gdal-bin \
    libgdal-dev \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Configura variáveis de ambiente para o compilador achar o GDAL
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

# Define diretório de trabalho
WORKDIR /app

# Copia os arquivos do projeto para dentro do container
# Certifique-se de que o arquivo .gpkg ou .zip do mapa esteja na mesma pasta
COPY . .

# Instala as dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Expõe a porta padrão do Streamlit
EXPOSE 8501

# Comando para rodar o app
# --server.address=0.0.0.0 é obrigatório para funcionar em cloud
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
