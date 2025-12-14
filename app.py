import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import json
import unicodedata
import geopandas as gpd
import os
from datetime import datetime, timedelta

# --- CONFIGURAÇÃO INICIAL E SEGURANÇA ---
st.set_page_config(
    page_title="Monitor de Colapso Urbano",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS PERSONALIZADO (PRODUÇÃO) ---
st.markdown("""
<style>
    /* Botões */
    .stButton>button {
        width: 100%;
        background-color: #2c2c2c;
        color: white;
        border-radius: 6px;
        height: 50px;
        font-weight: 700;
        transition: all 0.3s;
    }
    .stButton>button:hover {
        background-color: #444;
        border-color: #666;
    }
    
    /* Cards de Métricas */
    .metric-card {
        background-color: #111;
        padding: 20px;
        border-radius: 12px;
        text-align: center;
        box-shadow: 0 4px 10px rgba(0,0,0,0.5);
        margin-bottom: 15px;
        border: 1px solid #333;
    }
    .big-number {
        font-size: 3.5em;
        font-weight: 800;
        color: #fff;
        margin: 0;
        line-height: 1;
    }
    .metric-label {
        color: #aaa;
        font-size: 0.85em;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        margin-top: 8px;
        font-weight: 600;
    }

    /* Espaço de Publicidade */
    .ad-banner {
        background-color: #f8f9fa;
        border: 2px dashed #ccc;
        color: #666;
        padding: 15px;
        text-align: center;
        border-radius: 8px;
        margin-bottom: 20px;
        font-size: 0.9em;
    }
    
    /* Ajustes Gerais */
    .block-container { padding-top: 2rem; }
    h1, h2, h3 { color: #eee; }
</style>
""", unsafe_allow_html=True)

# --- FUNÇÕES AUXILIARES (DEFINIDAS NO TOPO PARA EVITAR NAMEERROR) ---

def normalize_text(text):
    if not isinstance(text, str): return ""
    text = text.upper()
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

def get_color_by_intensity(count, max_val, tipo):
    """Define a cor do polígono baseada na intensidade e tipo do problema."""
    ratio = count / max_val if max_val > 0 else 0
    if tipo == "Falta de Luz":
        # Gradiente PRETO/CINZA (Apagão)
        if ratio < 0.2: return '#bdbdbd'
        if ratio < 0.4: return '#969696'
        if ratio < 0.6: return '#737373'
        if ratio < 0.8: return '#525252'
        return '#000000'
    else:
        # Gradiente AZUL (Água)
        if ratio < 0.2: return '#bbdefb' # Azul muito claro
        if ratio < 0.4: return '#64b5f6' # Azul claro
        if ratio < 0.6: return '#2196f3' # Azul médio
        if ratio < 0.8: return '#1565c0' # Azul escuro
        return '#0d47a1'                 # Azul marinho profundo

def check_rate_limit():
    """Impede spam limitando envios."""
    now = datetime.now()
    if 'last_submission' in st.session_state:
        delta = (now - st.session_state['last_submission']).total_seconds()
        if delta < 60:
            return False, int(60 - delta)
    st.session_state['last_submission'] = now
    return True, 0

def manutencao_dados_antigos():
    """Remove reportes > 96h (Política de Retenção)."""
    if 'reports' in st.session_state and st.session_state['reports']:
        agora = datetime.now()
        limite = agora - timedelta(hours=96)
        st.session_state['reports'] = [
            r for r in st.session_state['reports'] 
            if r.get('timestamp', agora) > limite
        ]

# --- GERENCIAMENTO DE ESTADO ---

if 'reports' not in st.session_state:
    st.session_state['reports'] = []

if 'center_map' not in st.session_state:
    st.session_state['center_map'] = [-23.5505, -46.6333]

if 'geometries' not in st.session_state:
    st.session_state['geometries'] = {}

# Executa manutenção na inicialização
manutencao_dados_antigos()

# --- CARREGAMENTO DE DADOS E GEOMETRIA ---

# USAR cache_resource para manter o GeoDataFrame em memória RAM do servidor
@st.cache_resource
def load_geosampa_data():
    local_files = ["SIRGAS_GPKG_distrito.zip", "SIRGAS_GPKG_distrito.gpkg"]
    for filename in local_files:
        if os.path.exists(filename):
            try:
                file_path = filename
                if filename.endswith(".zip"):
                    file_path = f"zip://{filename}"
                
                # Lê APENAS o GeoDataFrame
                gdf = gpd.read_file(file_path)
                
                if gdf.crs != "EPSG:4326":
                    gdf = gdf.to_crs("EPSG:4326")
                
                # Cria coluna normalizada
                possible_cols = ['ds_nome', 'nm_distrito', 'name', 'NOME_DIST']
                name_col = next((c for c in possible_cols if c in gdf.columns), None)
                
                if name_col:
                    gdf['norm_name'] = gdf[name_col].apply(normalize_text)
                
                return gdf, name_col
                
            except Exception as e:
                print(f"Erro no carregamento local: {e}")
    
    return None, None

# Carrega a base uma vez (Lazy Loading global)
BASE_DATA = load_geosampa_data()

# --- BANCO DE DADOS DE CEPS (Compactado) ---
SP_CEP_DB = [
    {'min': 1000, 'max': 1099, 'dist': 'Sé', 'zona': 'Centro'},
    {'min': 1100, 'max': 1199, 'dist': 'Bom Retiro', 'zona': 'Centro'},
    {'min': 1200, 'max': 1299, 'dist': 'Consolação', 'zona': 'Centro'},
    {'min': 1300, 'max': 1399, 'dist': 'Bela Vista', 'zona': 'Centro'},
    {'min': 1400, 'max': 1499, 'dist': 'Jardim Paulista', 'zona': 'Centro'},
    {'min': 1500, 'max': 1599, 'dist': 'Liberdade', 'zona': 'Centro'},
    {'min': 2000, 'max': 2099, 'dist': 'Santana', 'zona': 'Zona Norte'},
    {'min': 2100, 'max': 2199, 'dist': 'Vila Maria', 'zona': 'Zona Norte'},
    {'min': 2200, 'max': 2299, 'dist': 'Tucuruvi', 'zona': 'Zona Norte'},
    {'min': 2300, 'max': 2399, 'dist': 'Tremembé', 'zona': 'Zona Norte'},
    {'min': 2400, 'max': 2499, 'dist': 'Mandaqui', 'zona': 'Zona Norte'},
    {'min': 2500, 'max': 2599, 'dist': 'Casa Verde', 'zona': 'Zona Norte'},
    {'min': 2600, 'max': 2699, 'dist': 'Cachoeirinha', 'zona': 'Zona Norte'},
    {'min': 2700, 'max': 2799, 'dist': 'Limão', 'zona': 'Zona Norte'},
    {'min': 2800, 'max': 2899, 'dist': 'Brasilândia', 'zona': 'Zona Norte'},
    {'min': 2900, 'max': 2999, 'dist': 'Freguesia do Ó', 'zona': 'Zona Norte'},
    {'min': 3000, 'max': 3099, 'dist': 'Brás', 'zona': 'Zona Leste'},
    {'min': 3100, 'max': 3199, 'dist': 'Mooca', 'zona': 'Zona Leste'},
    {'min': 3200, 'max': 3299, 'dist': 'Vila Prudente', 'zona': 'Zona Leste'},
    {'min': 3300, 'max': 3399, 'dist': 'Tatuapé', 'zona': 'Zona Leste'},
    {'min': 3400, 'max': 3499, 'dist': 'Carrão', 'zona': 'Zona Leste'},
    {'min': 3500, 'max': 3599, 'dist': 'Vila Matilde', 'zona': 'Zona Leste'},
    {'min': 3600, 'max': 3699, 'dist': 'Penha', 'zona': 'Zona Leste'},
    {'min': 3700, 'max': 3799, 'dist': 'Cangaíba', 'zona': 'Zona Leste'},
    {'min': 3800, 'max': 3899, 'dist': 'Ermelino Matarazzo', 'zona': 'Zona Leste'},
    {'min': 3900, 'max': 3999, 'dist': 'São Mateus', 'zona': 'Zona Leste'},
    {'min': 4000, 'max': 4099, 'dist': 'Vila Mariana', 'zona': 'Zona Sul'},
    {'min': 4100, 'max': 4199, 'dist': 'Saúde', 'zona': 'Zona Sul'},
    {'min': 4200, 'max': 4299, 'dist': 'Ipiranga', 'zona': 'Zona Sul'},
    {'min': 4300, 'max': 4399, 'dist': 'Jabaquara', 'zona': 'Zona Sul'},
    {'min': 4400, 'max': 4499, 'dist': 'Cidade Ademar', 'zona': 'Zona Sul'},
    {'min': 4500, 'max': 4599, 'dist': 'Itaim Bibi', 'zona': 'Zona Sul'},
    {'min': 4600, 'max': 4699, 'dist': 'Campo Belo', 'zona': 'Zona Sul'},
    {'min': 4700, 'max': 4799, 'dist': 'Santo Amaro', 'zona': 'Zona Sul'},
    {'min': 4800, 'max': 4899, 'dist': 'Cidade Dutra', 'zona': 'Zona Sul'},
    {'min': 4900, 'max': 4999, 'dist': 'Socorro', 'zona': 'Zona Sul'},
    {'min': 5000, 'max': 5099, 'dist': 'Lapa', 'zona': 'Zona Oeste'},
    {'min': 5100, 'max': 5199, 'dist': 'Pirituba', 'zona': 'Zona Oeste'},
    {'min': 5200, 'max': 5299, 'dist': 'Perus', 'zona': 'Zona Oeste'},
    {'min': 5300, 'max': 5399, 'dist': 'Vila Leopoldina', 'zona': 'Zona Oeste'},
    {'min': 5400, 'max': 5499, 'dist': 'Pinheiros', 'zona': 'Zona Oeste'},
    {'min': 5500, 'max': 5599, 'dist': 'Butantã', 'zona': 'Zona Oeste'},
    {'min': 5600, 'max': 5699, 'dist': 'Morumbi', 'zona': 'Zona Oeste'},
    {'min': 5700, 'max': 5799, 'dist': 'Campo Limpo', 'zona': 'Zona Oeste'},
    {'min': 5800, 'max': 5899, 'dist': 'Capão Redondo', 'zona': 'Zona Oeste'},
    {'min': 8000, 'max': 8099, 'dist': 'São Miguel', 'zona': 'Zona Leste'},
    {'min': 8100, 'max': 8199, 'dist': 'Itaim Paulista', 'zona': 'Zona Leste'},
    {'min': 8200, 'max': 8299, 'dist': 'Itaquera', 'zona': 'Zona Leste'},
    {'min': 8300, 'max': 8399, 'dist': 'São Mateus', 'zona': 'Zona Leste'},
    {'min': 8400, 'max': 8499, 'dist': 'Guaianases', 'zona': 'Zona Leste'},
]

def get_district_from_db(cep_str):
    try:
        prefix = int(cep_str[:5]) 
        for entry in SP_CEP_DB:
            if entry['min'] <= prefix <= entry['max']:
                return entry['dist'], entry['zona']
    except ValueError:
        pass
    return None, None

def get_district_geometry_from_base(distrito_nome, base_data):
    gdf, name_col = base_data
    if gdf is None or name_col is None: return None, None
    
    target_name = normalize_text(distrito_nome)
    
    match = gdf[gdf['norm_name'] == target_name]
    if match.empty:
        match = gdf[gdf['norm_name'].str.contains(target_name, na=False)]
    
    if not match.empty:
        try:
            feature = match.iloc[0]
            feature_json = json.loads(gpd.GeoSeries([feature.geometry]).to_json())
            geojson_feature = feature_json['features'][0]
            centroid = feature.geometry.centroid
            return geojson_feature, [centroid.y, centroid.x]
        except Exception as e:
            print(f"Erro geometria: {e}")
            return None, [-23.5505, -46.6333]
    return None, None

def processar_reporte(cep_input, tipo_problema):
    # 1. Rate Limit
    allowed, wait_time = check_rate_limit()
    if not allowed:
        st.warning(f"⏳ Aguarde {wait_time}s para enviar novamente.")
        return

    # 2. Input
    if not cep_input:
        st.warning("⚠️ Digite um CEP.")
        return

    clean_cep = "".join(filter(str.isdigit, str(cep_input)))
    if len(clean_cep) != 8:
        st.error("❌ CEP Inválido.")
        return

    # 3. Processamento
    distrito_db, zona_db = get_district_from_db(clean_cep)
    
    if distrito_db:
        geojson, coords = get_district_geometry_from_base(distrito_db, BASE_DATA)
        lat, lon = coords if coords else (-23.5505, -46.6333)
        
        st.session_state['reports'].append({
            'lat': lat,
            'lon': lon,
            'cep': clean_cep,
            'regiao': distrito_db,
            'zona': zona_db,
            'cidade': "São Paulo",
            'uf': "SP",
            'type': tipo_problema,
            'timestamp': datetime.now()
        })
        
        st.session_state['center_map'] = [lat, lon]
        key = f"{distrito_db} - São Paulo"
        if geojson:
            st.session_state['geometries'][key] = geojson
        
        st.success(f"✅ Registrado: {distrito_db} ({zona_db})")
    else:
        st.error("❌ CEP não encontrado na cobertura.")

# --- INTERFACE ---

st.title("Monitor de Colapso Urbano")

st.markdown("""
<div class="ad-banner">
    <b>ESPAÇO PUBLICITÁRIO</b><br>
    Sua marca aqui. Apoie o monitoramento colaborativo.
</div>
""", unsafe_allow_html=True)

col1, col2 = st.columns([1, 2.5])

with col1:
    st.subheader("Reportar Ocorrência")
    
    tipo_problema = st.radio(
        "Problema:",
        ["Falta de Luz", "Falta de Água"],
        horizontal=True
    )
    
    cep_input = st.text_input("CEP (Somente números)", placeholder="00000000", max_chars=8)
    
    if st.button("📢 Confirmar"):
        processar_reporte(cep_input, tipo_problema)
    
    st.markdown("---")
    
    df_all = pd.DataFrame(st.session_state['reports'])
    if not df_all.empty and 'type' not in df_all.columns:
        df_all['type'] = 'Falta de Luz'
        
    df_filtered = df_all[df_all['type'] == tipo_problema] if not df_all.empty else pd.DataFrame()

    if not df_filtered.empty:
        st.markdown(f"""
        <div class="metric-card">
            <p class="big-number">{len(df_filtered)}</p>
            <p class="metric-label">Reportes Ativos ({tipo_problema})</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.subheader("Zonas Críticas")
        ranking = df_filtered.groupby(['zona', 'regiao']).size().reset_index(name='Qtd')
        ranking = ranking.sort_values(by='Qtd', ascending=False)
        
        st.dataframe(
            ranking, 
            hide_index=True, 
            use_container_width=True,
            column_config={
                "zona": "Zona",
                "regiao": "Distrito",
                "Qtd": st.column_config.ProgressColumn(
                    "Intensidade",
                    format="%d",
                    min_value=0,
                    max_value=max(ranking['Qtd']),
                )
            }
        )
    else:
        st.info(f"Sem reportes de {tipo_problema} recentes.")

with col2:
    m = folium.Map(
        location=st.session_state['center_map'],
        zoom_start=11 if not df_filtered.empty else 10,
        tiles="CartoDB Positron"
    )

    if not df_filtered.empty:
        regiao_group = df_filtered.groupby(['regiao', 'cidade', 'uf']).size().reset_index(name='count')
        max_reports = regiao_group['count'].max()
        
        for _, row in regiao_group.iterrows():
            regiao_nome = row['regiao']
            cidade_nome = row['cidade']
            count = row['count']
            
            key = f"{regiao_nome} - {cidade_nome}"
            geojson_data = st.session_state['geometries'].get(key)
            fill_color = get_color_by_intensity(count, max_reports, tipo_problema)
            
            if geojson_data:
                folium.GeoJson(
                    geojson_data,
                    style_function=lambda x, color=fill_color: {
                        'fillColor': color,
                        'color': '#ffffff',
                        'weight': 3,
                        'fillOpacity': 0.6
                    },
                    tooltip=f"{regiao_nome}: {count}"
                ).add_to(m)
            else:
                sample_coord = df_filtered[df_filtered['regiao'] == regiao_nome].iloc[0]
                folium.Circle(
                    location=[sample_coord['lat'], sample_coord['lon']],
                    radius=1000,
                    color='#ffffff',
                    weight=3,
                    fill=True,
                    fill_color=fill_color,
                    fill_opacity=0.6,
                    tooltip=f"{regiao_nome}"
                ).add_to(m)
        
    st_folium(m, width="100%", height=600)
