import streamlit as st

# Configuração básica
st.set_page_config(page_title="Teste Conexão", page_icon="🟢")

# Conteúdo Mínimo
st.title("🟢 Servidor Online!")
st.success("Se você vê esta mensagem, a conexão HTTP, o Docker e o Streamlit estão funcionando perfeitamente.")

st.write("O erro 502 anterior foi causado provavelmente pelo peso das bibliotecas geográficas (GeoPandas/GDAL) estourando a memória na inicialização.")
