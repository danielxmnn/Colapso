import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import json
import unicodedata
import geopandas as gpd
import os
import requests
from datetime import datetime, timedelta
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
import streamlit.components.v1 as components

# --- CONFIGURAÇÃO INICIAL ---
st.set_page_config(
    page_title="Monitor de Colapso Urbano",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS PERSONALIZADO (PRODUÇÃO) ---
st.markdown("""
<style>
    /* --- REMOVE MENU DE DESENVOLVEDOR E RODAPÉ STREAMLIT --- */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    [data-testid="stToolbar"] {visibility: hidden;} /* Remove barra de deploy superior */
    
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

    /* Container de Publicidade */
    .ad-container {
        background-color: #f0f2f6;
        border: 1px solid #e0e0e0;
        text-align: center;
        padding: 10px;
        margin-bottom: 20px;
        border-radius: 8px;
        min-height: 90px;
        display: flex;
        align-items: center;
        justify-content: center;
        color: #888;
        font-size: 0.8em;
    }
    
    /* Ajustes Gerais */
    .block-container { padding-top: 2rem; }
    h1, h2, h3 { color: #eee; }
</style>
""", unsafe_allow_html=True)

# --- FUNÇÕES AUXILIARES ---

def normalize_text(text):
    if not isinstance(text, str): return ""
    text = text.upper()
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

def get_color_by_intensity(count, max_val, tipo):
    """Define a cor do polígono baseada na intensidade e tipo do problema."""
    ratio = count / max_val if max_val > 0 else 0
    if tipo == "Falta de Luz":
        # Gradiente PRETO/CINZA
        if ratio < 0.2: return '#bdbdbd'
        if ratio < 0.4: return '#969696'
        if ratio < 0.6: return '#737373'
        if ratio < 0.8: return '#525252'
        return '#000000'
    else:
        # Gradiente AZUL
        if ratio < 0.2: return '#bbdefb'
        if ratio < 0.4: return '#64b5f6'
        if ratio < 0.6: return '#2196f3'
        if ratio < 0.8: return '#1565c0'
        return '#0d47a1'

def check_rate_limit():
    """Impede spam limitando envios a 1 a cada 60s por sessão."""
    now = datetime.now()
    if 'last_submission' in st.session_state:
        delta = (now - st.session_state['last_submission']).total_seconds()
        if delta < 60:
            return False, int(60 - delta)
    st.session_state['last_submission'] = now
    return True, 0

def manutencao_dados_antigos():
    """Remove reportes > 96h."""
    if 'reports' in st.session_state and st.session_state['reports']:
        agora = datetime.now()
        limite = agora - timedelta(hours=96)
        st.session_state['reports'] = [
            r for r in st.session_state['reports'] 
            if r.get('timestamp', agora) > limite
        ]

def buscar_cep_por_endereco(endereco):
    """Busca CEP via Nominatim (OpenStreetMap)."""
    geolocator = Nominatim(user_agent="monitor_colapso_urbano_v1")
    try:
        query = f"{endereco}, Brazil"
        location = geolocator.geocode(query, addressdetails=True, timeout=10)
        
        if location:
            address_info = location.raw.get('address', {})
            cep = address_info.get('postcode')
            if cep:
                return cep.replace("-", "").replace(" ", "")
    except Exception as e:
        print(f"Erro na busca de endereço: {e}")
    return None

# --- GERENCIAMENTO DE ESTADO ---

if 'reports' not in st.session_state:
    st.session_state['reports'] = []

if 'center_map' not in st.session_state:
    st.session_state['center_map'] = [-23.5505, -46.6333]

if 'geometries' not in st.session_state:
    st.session_state['geometries'] = {}

if 'cep_value' not in st.session_state:
    st.session_state['cep_value'] = ""

manutencao_dados_antigos()

# --- CARREGAMENTO DE DADOS (SP) ---

@st.cache_resource
def load_geosampa_data():
    local_files = ["SIRGAS_GPKG_distrito.zip", "SIRGAS_GPKG_distrito.gpkg"]
    for filename in local_files:
        if os.path.exists(filename):
            try:
                file_path = filename
                if filename.endswith(".zip"):
                    file_path = f"zip://{filename}"
                
                gdf = gpd.read_file(file_path)
                if gdf.crs != "EPSG:4326":
                    gdf = gdf.to_crs("EPSG:4326")
                
                possible_cols = ['ds_nome', 'nm_distrito', 'name', 'NOME_DIST']
                name_col = next((c for c in possible_cols if c in gdf.columns), None)
                if name_col:
                    gdf['norm_name'] = gdf[name_col].apply(normalize_text)
                return gdf, name_col
            except Exception as e:
                print(f"Erro no carregamento local: {e}")
    return None, None

BASE_DATA_SP = load_geosampa_data()

# --- BANCO DE DADOS DE CEPS (SP CAPITAL) ---
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

def get_data_from_brasilapi(cep):
    """Fallback Nacional."""
    try:
        url = f"https://brasilapi.com.br/api/cep/v2/{cep}"
        response = requests.get(url, timeout=3)
        if response.status_code == 200:
            data = response.json()
            if 'location' in data and 'coordinates' in data['location']:
                coords = data['location']['coordinates']
                lat = float(coords.get('latitude', 0))
                lon = float(coords.get('longitude', 0))
                bairro = data.get('neighborhood', 'Centro')
                cidade = data.get('city', 'Cidade')
                uf = data.get('state', 'BR')
                if lat != 0 and lon != 0:
                    return bairro, cidade, uf, lat, lon
    except Exception as e:
        print(f"Erro BrasilAPI: {e}")
    return None

def get_district_geometry_sp(distrito_nome, base_data):
    """Geometria para SP."""
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
        except:
            pass
    return None, None

def processar_reporte(cep_input, tipo_problema):
    # 1. Rate Limit
    allowed, wait_time = check_rate_limit()
    if not allowed:
        st.warning(f"⏳ Aguarde {wait_time}s.")
        return

    # 2. Input
    if not cep_input:
        st.warning("⚠️ Digite um CEP.")
        return
    clean_cep = "".join(filter(str.isdigit, str(cep_input)))
    if len(clean_cep) != 8:
        st.error("❌ CEP Inválido.")
        return

    # 3. Lógica Híbrida (SP vs Nacional)
    sp_data = None
    try:
        prefix = int(clean_cep[:5])
        for entry in SP_CEP_DB:
            if entry['min'] <= prefix <= entry['max']:
                sp_data = entry
                break
    except:
        pass

    if sp_data:
        # SP Capital
        distrito = sp_data['dist']
        zona = sp_data['zona']
        cidade = "São Paulo"
        uf = "SP"
        geojson, coords = get_district_geometry_sp(distrito, BASE_DATA_SP)
        lat, lon = coords if coords else (-23.5505, -46.6333)
        has_geometry = bool(geojson)
    else:
        # Resto do Brasil (BrasilAPI)
        api_data = get_data_from_brasilapi(clean_cep)
        if api_data:
            distrito, cidade, uf, lat, lon = api_data
            zona = f"{cidade}/{uf}"
            geojson = None
            has_geometry = False
        else:
            st.error("❌ CEP não encontrado na base nacional.")
            return

    # 4. Salvar
    st.session_state['reports'].append({
        'lat': lat,
        'lon': lon,
        'cep': clean_cep,
        'regiao': distrito,
        'zona': zona,
        'cidade': cidade,
        'uf': uf,
        'type': tipo_problema,
        'timestamp': datetime.now(),
        'has_geometry': has_geometry
    })
    
    st.session_state['center_map'] = [lat, lon]
    if has_geometry and geojson:
        key = f"{distrito} - {cidade}"
        st.session_state['geometries'][key] = geojson
    
    st.success(f"✅ Registrado: {distrito} - {cidade}/{uf}")

# --- INTERFACE ---

st.title("Monitor de Colapso Urbano")

# ÁREA DE PUBLICIDADE (ADSENSE REAL)
def render_ad_header():
    # ID do Cliente: ca-pub-9651406703551753
    # NOTA: O 'data-ad-slot' deve ser preenchido após criar o bloco de anúncios no painel do Google.
    ad_html = """
    <div class="ad-container">
        <meta name="google-adsense-account" content="ca-pub-9651406703551753">
        <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-9651406703551753"
             crossorigin="anonymous"></script>
        
        <!-- Bloco de Anúncio -->
        <ins class="adsbygoogle"
             style="display:block"
             data-ad-client="ca-pub-9651406703551753"
             data-ad-slot="XXXXXXXXXX"
             data-ad-format="auto"
             data-full-width-responsive="true"></ins>
        <script>
             (adsbygoogle = window.adsbygoogle || []).push({});
        </script>
        <div style="padding:5px; color:#999; font-size:10px;">Publicidade (Google Ads)</div>
    </div>
    """
    components.html(ad_html, height=140)

render_ad_header()

col1, col2 = st.columns([1, 2.5])

with col1:
    st.subheader("Reportar Ocorrência")
    
    tipo_problema = st.radio(
        "Problema:",
        ["Falta de Luz", "Falta de Água"],
        horizontal=True
    )
    
    # Busca de Endereço
    with st.expander("📍 Não sabe o CEP? Buscar por endereço"):
        end_busca = st.text_input("Endereço (Ex: Av. Paulista, 1000, SP)")
        if st.button("🔍 Pesquisar CEP"):
            with st.spinner("Buscando..."):
                cep_encontrado = buscar_cep_por_endereco(end_busca)
                if cep_encontrado:
                    st.session_state['cep_value'] = cep_encontrado
                    st.success(f"CEP: {cep_encontrado}")
                    st.rerun()
                else:
                    st.error("Endereço não localizado.")

    cep_input = st.text_input(
        "CEP (Somente números)", 
        value=st.session_state['cep_value'],
        placeholder="00000000", 
        max_chars=8,
        key="cep_input_widget"
    )
    
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
            <p class="metric-label">Reportes ({tipo_problema})</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.subheader("Locais Críticos")
        ranking = df_filtered.groupby(['cidade', 'uf', 'regiao']).size().reset_index(name='Qtd')
        ranking = ranking.sort_values(by='Qtd', ascending=False)
        
        st.dataframe(
            ranking, 
            hide_index=True, 
            use_container_width=True,
            column_config={
                "cidade": "Cidade",
                "uf": "UF",
                "regiao": "Bairro/Distrito",
                "Qtd": st.column_config.ProgressColumn(
                    "Alertas",
                    format="%d",
                    min_value=0,
                    max_value=max(ranking['Qtd']),
                )
            }
        )
    else:
        st.info(f"Sem reportes recentes.")

with col2:
    m = folium.Map(
        location=st.session_state['center_map'],
        zoom_start=10,
        tiles="CartoDB Positron"
    )

    if not df_filtered.empty:
        grouped = df_filtered.groupby(['regiao', 'cidade']).agg({
            'lat': 'first', 'lon': 'first', 'type': 'count', 'has_geometry': 'first'
        }).rename(columns={'type': 'count'}).reset_index()
        
        max_reports = grouped['count'].max()
        
        for _, row in grouped.iterrows():
            count = row['count']
            has_geom = row['has_geometry']
            key = f"{row['regiao']} - {row['cidade']}"
            geojson_data = st.session_state['geometries'].get(key) if has_geom else None
            fill_color = get_color_by_intensity(count, max_reports, tipo_problema)
            
            if geojson_data:
                folium.GeoJson(
                    geojson_data,
                    style_function=lambda x, color=fill_color: {
                        'fillColor': color, 'color': '#ffffff', 'weight': 2, 'fillOpacity': 0.6
                    },
                    tooltip=f"{row['regiao']}: {count}"
                ).add_to(m)
            else:
                folium.Circle(
                    location=[row['lat'], row['lon']],
                    radius=800, color='#ffffff', weight=2, fill=True,
                    fill_color=fill_color, fill_opacity=0.6,
                    tooltip=f"{row['regiao']}: {count}"
                ).add_to(m)
        
    st_folium(m, width="100%", height=600)
