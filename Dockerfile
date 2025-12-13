# Usa uma imagem Python super leve para subir rápido
FROM python:3.9-slim

# Define diretório de trabalho
WORKDIR /app

# Copia os arquivos
COPY . .

# Instala apenas o básico para o teste de conexão
RUN pip install --no-cache-dir -r requirements.txt

# O EXPOSE é apenas documentação, o que vale é o CMD abaixo
EXPOSE 8501

# --- CORREÇÃO DO ERRO 502 ---
# Usamos 'sh -c' para permitir o uso de variáveis de ambiente ($PORT).
# Se a plataforma der uma porta (ex: Railway), usamos ela.
# Se não der (local), usamos 8501.
CMD sh -c 'streamlit run app.py --server.port=${PORT:-8501} --server.address=0.0.0.0'
