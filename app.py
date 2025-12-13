import streamlit as st
import os
import pandas as pd

# --- CONFIGURAÇÃO LEVE ---
st.set_page_config(
    page_title="Teste de Diagnóstico",
    page_icon="🛠️",
    layout="wide"
)

st.title("🛠️ Monitor - Modo de Diagnóstico")
st.markdown("Se você está vendo esta tela, o **Servidor Web subiu com sucesso** (adeus erro 502 na inicialização!).")

# --- TESTE 1: VERIFICAÇÃO DE ARQUIVOS ---
st.subheader("1. Verificação de Arquivos Locais")
map_files = ["SIRGAS_GPKG_distrito.zip", "SIRGAS_GPKG_distrito.gpkg"]
found_map = False

for f in map_files:
    if os.path.exists(f):
        size_mb = os.path.getsize(f) / (1024 * 1024)
        st.success(f"✅ Arquivo encontrado: `{f}` ({size_mb:.2f} MB)")
        found_map = True
    else:
        st.warning(f"❌ Arquivo não encontrado: `{f}`")

if not found_map:
    st.error("⚠️ CRÍTICO: Nenhum arquivo de mapa encontrado. O deploy falhará se tentarmos carregar.")

# --- TESTE 2: CARREGAMENTO DE BIBLIOTECAS PESADAS ---
st.subheader("2. Teste de Importação (Geopandas/GDAL)")
st.markdown("Clique abaixo para tentar importar as bibliotecas de mapa. Se o servidor tiver pouca memória, ele pode cair aqui.")

if st.button("Carregar GeoPandas e Folium"):
    try:
        with st.spinner("Importando bibliotecas..."):
            import geopandas as gpd
            import folium
            from streamlit_folium import st_folium
            st.success("✅ Sucesso! As bibliotecas GDAL/GeoPandas estão instaladas corretamente.")
            
            # Se chegou aqui, tenta ler apenas as primeiras 5 linhas do arquivo (Teste de Leitura)
            if found_map:
                try:
                    file_to_load = "SIRGAS_GPKG_distrito.gpkg" if os.path.exists("SIRGAS_GPKG_distrito.gpkg") else "zip://SIRGAS_GPKG_distrito.zip"
                    
                    st.info(f"Tentando ler cabeçalho do mapa: {file_to_load}...")
                    # rows=5 é crucial para não estourar a memória num teste
                    gdf_sample = gpd.read_file(file_to_load, rows=5) 
                    
                    st.write("Amostra de dados carregada com sucesso:")
                    st.write(gdf_sample.head())
                    st.success("✅ Leitura de arquivo GPKG funcionando!")
                    
                except Exception as e:
                    st.error(f"❌ Erro ao ler o arquivo de mapa: {e}")
            
    except ImportError as e:
        st.error(f"❌ Erro de Instalação: Biblioteca não encontrada ({e}). Verifique o requirements.txt.")
    except Exception as e:
        st.error(f"❌ Erro Genérico ao importar: {e}")

st.markdown("---")
st.caption("Se este teste passar, o problema original era o carregamento 'guloso' do mapa inteiro na inicialização.")
