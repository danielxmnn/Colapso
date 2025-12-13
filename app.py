import streamlit as st
import os

# Configuração básica
st.set_page_config(page_title="Teste de Porta", page_icon="🔌")

# Conteúdo de Diagnóstico
st.title("🔌 Conexão Estabelecida!")

# Mostra qual porta o servidor escolheu (Debug)
port_used = os.environ.get("PORT", "8501 (Padrão)")

st.success(f"""
### Status: ONLINE
O servidor web subiu corretamente.
- **Porta Detectada:** {port_used}
- **Endereço:** 0.0.0.0
""")

st.info("Agora que confirmamos que o deploy funciona, podemos voltar a adicionar as bibliotecas de mapa (GeoPandas) e o código completo.")
