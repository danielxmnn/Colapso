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

# --- FUNÇÕES DE SEGURANÇA E REDE ---

def validate_cloudflare_headers():
    """
    Validação Flexível de Segurança.
    Só bloqueia se a variável de ambiente PROD_MODE estiver 'true'.
    """
    # Verifica se estamos em modo PRODUÇÃO ESTRITA
    strict_mode = os.environ.get("PROD_MODE", "false").lower() == "true"
    
    try:
        if hasattr(st, "context") and hasattr(st.context, "headers"):
            headers = st.context.headers
            required_headers = ["CF-Connecting-IP", "CF-RAY", "CF-Visitor"]
            missing = [h for h in required_headers if h not in headers]
            
            if missing:
                if strict_mode:
                    return False, f"Bloqueio de Segurança (Prod). Headers ausentes: {missing}"
                else:
                    # Em modo Dev/Deploy inicial, permite mas avisa no log
                    print(f"⚠️ AVISO: Acesso direto detectado (Headers: {missing}). Permitido pois PROD_MODE != true.")
                    return True, "Dev Mode (Direct Access)"
            
            return True, headers["CF-Connecting-IP"]
            
        # Fallback para ambiente local
        if strict_mode:
            return False, "Contexto de cabeçalhos indisponível em PROD_MODE."
        return True, "Localhost/Dev"
        
    except Exception as e:
        if strict_mode:
            return False, str(e)
        return True, f"Erro ignorado em Dev: {e}"

def check_rate_limit():
    """
    Impede spam limitando envios a 1 a cada 60 segundos por sessão.
    """
    now = datetime.now()
    if 'last_submission' in st.session_state:
        delta = (now - st.session_state['last_submission']).total_seconds()
        if delta < 60:
            return False, int(60 - delta)
    
    st.session_state['last_submission'] = now
    return True, 0

# --- GERENCIAMENTO DE ESTADO E DADOS ---

if 'reports' not in st.session_state:
    st.session_state['reports'] = []

if 'center_map' not in st.session_state:
    st.session_state['center_map'] = [-23.5505, -46.6333]

if 'geometries' not in st.session_state:
    st.session_state['geometries'] = {}

def manutencao_dados_antigos():
    """Remove reportes > 96h (Política de Retenção)."""
    if st.session_state['reports']:
        agora = datetime.now()
        limite = agora - timedelta(hours=96)
        st.session_state['reports'] = [
            r for r in st.session_state['reports'] 
            if r.get('timestamp', agora) > limite
        ]

manutencao_dados_antigos()

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

# --- FUNÇÕES DE LÓGICA DE NEGÓCIO ---

def normalize_text(text):
    if not isinstance(text, str): return ""
    text = text.upper()
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

@st.cache_data
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
                return json.loads(gdf.to_json())
            except Exception as e:
                # Em produção, logar o erro internamente em vez de mostrar ao usuário
                print(f"Erro no carregamento local: {e}")
    
    st.error("⚠️ ERRO DE CONFIGURAÇÃO: Base cartográfica não encontrada. Contate o suporte.")
    return None

def get_district_from_db(cep_str):
    try:
        prefix = int(cep_str[:5]) 
        for entry in SP_CEP_DB:
            if entry['min'] <= prefix <= entry['max']:
                return entry['dist'], entry['zona']
    except ValueError:
        pass
    return None, None

def get_district_geometry_from_base(distrito_nome, geojson_data):
    if not geojson_data: return None, None
    target_name = normalize_text(distrito_nome)
    
    for feature in geojson_data['features']:
        props = feature.get('properties', {})
        feature_name = normalize_text(
            props.get('ds_nome', '') or props.get('nm_distrito', '') or 
            props.get('name', '') or props.get('NOME_DIST', '')
        )
        
        if target_name == feature_name or (target_name in feature_name and len(target_name) > 3):
            try:
                if feature['geometry']['type'] == 'Polygon':
                    coords = feature['geometry']['coordinates'][0][0]
                elif feature['geometry']['type'] == 'MultiPolygon':
                    coords = feature['geometry']['coordinates'][0][0][0]
                else:
                    coords = [-46.6333, -23.5505]
                return feature, [coords[1], coords[0]]
            except:
                return feature, [-23.5505, -46.6333]
    return None, None

def get_color_by_intensity(count, max_val, tipo):
    ratio = count / max_val if max_val > 0 else 0
    if tipo == "Falta de Luz":
        if ratio < 0.2: return '#bdbdbd'
        if ratio < 0.4: return '#969696'
        if ratio < 0.6: return '#737373'
        if ratio < 0.8: return '#525252'
        return '#000000'
    else:
        if ratio < 0.2: return '#bbdefb'
        if ratio < 0.4: return '#64b5f6'
        if ratio < 0.6: return '#2196f3'
        if ratio < 0.8: return '#1565c0'
        return '#0d47a1'

def processar_reporte(cep_input, tipo_problema):
    # 0. Validação de Segurança (Cloudflare Strict - Opcional via ENV)
    # MUDANÇA: Tornamos isso apenas um aviso se falhar, a menos que PROD_MODE esteja ativado explicitamente.
    is_secure, client_ip_or_error = validate_cloudflare_headers()
    
    if not is_secure:
        # Se falhar a segurança estrita, mostramos erro e paramos.
        st.error(f"⛔ ACESSO NEGADO: Requisição inválida ou insegura.\nDetalhe: {client_ip_or_error}")
        return 

    # 1. Validação de Rate Limit
    allowed, wait_time = check_rate_limit()
    if not allowed:
        st.warning(f"⏳ Por favor, aguarde {wait_time} segundos antes de enviar outro reporte.")
        return

    # 2. Validação de Input
    if not cep_input:
        st.warning("⚠️ O campo CEP é obrigatório.")
        return

    clean_cep = "".join(filter(str.isdigit, str(cep_input)))
    if len(clean_cep) != 8:
        st.error("❌ CEP Inválido. Digite os 8 números.")
        return

    # 3. Processamento
    BASE_GEOJSON = load_geosampa_data()
    if not BASE_GEOJSON: return

    distrito_db, zona_db = get_district_from_db(clean_cep)
    
    if distrito_db:
        geojson, coords = get_district_geometry_from_base(distrito_db, BASE_GEOJSON)
        
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
        
        st.success(f"✅ Reporte Registrado: {distrito_db} ({zona_db})")
    else:
        st.error("❌ CEP não encontrado na área de cobertura.")

# --- INTERFACE PRINCIPAL ---

st.title("Monitor de Colapso Urbano")

# BANNER DE PUBLICIDADE (TOPO)
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
        "Selecione o problema:",
        ["Falta de Luz", "Falta de Água"],
        horizontal=True
    )
    
    cep_input = st.text_input("CEP (Somente números)", placeholder="00000000", max_chars=8)
    
    if st.button("📢 Confirmar e Enviar"):
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
        st.info(f"Sistema Operante. Sem reportes de {tipo_problema} nas últimas 96h.")

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
