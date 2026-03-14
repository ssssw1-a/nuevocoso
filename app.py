import streamlit as st
import pandas as pd
import json
import os
import re
import pdfplumber
import io
import urllib.parse

# --- CONFIGURACIÓN ESTÉTICA DE LA PLATAFORMA ---
st.set_page_config(
    page_title="Variedades Juancho - Sistema Pro",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilo personalizado para mejorar la visibilidad de agotados
st.markdown("""
    <style>
    .stMetric { background-color: #ffffff; border-radius: 15px; padding: 15px; border: 1px solid #e2e8f0; }
    [data-testid="stMetricDelta"] svg { display: none; }
    </style>
""", unsafe_allow_stdio=True)

# --- BASE DE DATOS LOCAL PERMANENTE ---
DB_FILE = "juancho_inventory_db.json"

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

def save_db(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# --- LÓGICA DE LIMPIEZA QUIRÚRGICA ---
def clean_string(val):
    if val is None: return ""
    # Eliminar guiones bajos y espacios dobles del sistema
    return str(val).replace('_', '').strip().replace('  ', ' ')

def parse_units_and_price(val):
    """
    Corrige el error de las unidades (1.00 -> 1) 
    y precios (15.000 -> 15000)
    """
    if not val: return 0.0
    s = clean_string(val).replace(',', '.')
    
    # Si hay un punto seguido de exactamente 3 números (miles)
    if re.search(r'\.\d{3}$', s):
        s = s.replace('.', '')
    
    try:
        num = float(s)
        # Si el número termina en .0, lo convertimos en entero para que se vea limpio
        return int(num) if num == int(num) else num
    except:
        return 0.0

def process_sistecredito_file(file):
    processed = []
    
    if file.name.lower().endswith('.pdf'):
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text: continue
                lines = text.split('\n')
                for line in lines:
                    # Buscamos líneas que empiecen con código (ej: 02949) seguido de barras (ej: 9000...)
                    match = re.search(r'^(\d{4,})\s+(\d{8,})\s+(.+)', line)
                    if match:
                        codigo_int = match.group(1)
                        codigo_bar = match.group(2)
                        resto = match.group(3).split(' ')
                        
                        # Extraer precio y unidades que suelen estar al final
                        # Filtramos palabras que parezcan números
                        nums = [p for p in resto if re.search(r'\d', p)]
                        nombre_parts = [p for p in resto if not re.search(r'^\d', p) or '.' in p]
                        
                        unidades = 0
                        precio = 0
                        
                        # Lógica de asignación por posición final
                        if len(nums) >= 2:
                            precio = parse_units_and_price(nums[-2])
                            unidades = parse_units_and_price(nums[-1])
                        elif len(nums) == 1:
                            precio = parse_units_and_price(nums[0])
                            unidades = 0
                            
                        processed.append({
                            "Código Interno": codigo_int,
                            "Código de Barras": codigo_bar,
                            "Nombre": " ".join(nombre_parts).upper().strip(),
                            "Referencia": nombre_parts[-1] if nombre_parts else "N/A",
                            "Precio": precio,
                            "Unidades": unidades
                        })
    else:
        # Lógica para XLS / CSV
        df_raw = pd.read_excel(file) if file.name.endswith(('.xls', '.xlsx')) else pd.read_csv(file)
        for _, row in df_raw.iterrows():
            vals = [clean_string(v) for v in row.values if clean_string(v) != ""]
            if len(vals) >= 4 and vals[0].isdigit():
                processed.append({
                    "Código Interno": vals[0],
                    "Código de Barras": vals[1],
                    "Nombre": vals[2].upper(),
                    "Referencia": vals[3] if len(vals) > 4 else "N/A",
                    "Precio": parse_units_and_price(vals[-2] if len(vals) > 5 else vals[-1]),
                    "Unidades": parse_smart_unit(vals[-1]) if len(vals) > 5 else 0
                })
    return processed

def parse_smart_unit(val):
    # Función auxiliar para asegurar que las unidades no tengan ceros basura
    n = parse_units_and_price(val)
    return int(n) if n == int(n) else n

# --- INTERFAZ DE USUARIO ---
if 'inventory' not in st.session_state:
    st.session_state.inventory = load_db()

# Sidebar profesional
with st.sidebar:
    st.title("🛡️ Admin Juancho")
    st.subheader("Base de Datos Local")
    
    file = st.file_uploader("Actualizar Inventario (PDF/XLS)", type=['pdf', 'xls', 'xlsx', 'csv'])
    
    if file:
        with st.spinner("Limpiando y sincronizando datos..."):
            data = process_sistecredito_file(file)
            if data:
                st.session_state.inventory = data
                save_db(data)
                st.toast("¡Base de datos actualizada!", icon="✅")
                st.rerun()

    st.markdown("---")
    if st.button("🗑️ Vaciar Inventario"):
        if st.checkbox("Confirmar eliminación permanente"):
            st.session_state.inventory = []
            save_db([])
            st.rerun()

# --- DASHBOARD ---
st.title("📦 Gestión de Inventario Variedades Juancho")

if not st.session_state.inventory:
    st.warning("⚠️ No hay datos cargados. Por favor, importa el archivo de Sistecrédito desde el panel lateral.")
else:
    df = pd.DataFrame(st.session_state.inventory)
    
    # Métricas Superiores
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Referencias", len(df))
    
    agotados = len(df[df['Unidades'] <= 0])
    c2.metric("Agotados (Stock 0)", agotados, delta=f"{agotados} críticos", delta_color="inverse")
    
    valor_total = (df['Precio'] * df['Unidades']).sum()
    c3.metric("Valor Inversión", f"${valor_total:,.0f}")

    # Pestañas de Trabajo
    tab_list, tab_stats = st.tabs(["🔍 Buscador Inteligente", "📊 Análisis de Ventas"])

    with tab_list:
        # Buscador y Filtro
        col_search, col_filter = st.columns([3, 1])
        query = col_search.text_input("Buscar por Nombre, Código o Barras:", placeholder="Ej: BICICLETA...")
        hide_empty = col_filter.checkbox("Ocultar Agotados", value=False)
        
        # Procesar visualización
        view_df = df.copy()
        if hide_empty: view_df = view_df[view_df['Unidades'] > 0]
        if query:
            view_df = view_df[
                view_df['Nombre'].str.contains(query, case=False) |
                view_df['Código Interno'].str.contains(query) |
                view_df['Código de Barras'].str.contains(query)
            ]

        # Enlace a Google
        view_df['Google'] = view_df['Nombre'].apply(lambda x: f"https://www.google.com/search?q={urllib.parse.quote(str(x))}")

        # Editor de Datos (Tabla Profesional)
        st.data_editor(
            view_df,
            column_config={
                "Precio": st.column_config.NumberColumn("Precio", format="$ %d"),
                "Unidades": st.column_config.NumberColumn("Stock", format="%d"),
                "Google": st.column_config.LinkColumn("Google", display_text="🔍"),
            },
            hide_index=True,
            use_container_width=True,
            disabled=True # Solo lectura
        )

    with tab_stats:
        col_left, col_right = st.columns(2)
        
        with col_left:
            st.subheader("💎 Productos Más Caros")
            st.dataframe(df.nlargest(5, 'Precio')[['Nombre', 'Precio']], hide_index=True, use_container_width=True)
            
        with col_right:
            st.subheader("🚨 Prioridad de Reposición")
            st.dataframe(df[df['Unidades'] <= 0].head(10)[['Nombre', 'Código Interno']], hide_index=True, use_container_width=True)

    # Exportar Reporte
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Descargar Reporte Limpio (CSV)",
        data=csv,
        file_name='inventario_juancho_limpio.csv',
        mime='text/csv',
    )

st.markdown("---")
st.caption("Variedades Juancho Pro System • 2026 • Trujillo S. Juan Pablo")
