import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

# Konfigurasi
BUCKET_NAME = "stock-csvku"
FILE_NAME = "hasil_gabungan.parquet"
GCS_PATH = f"gs://{BUCKET_NAME}/{FILE_NAME}"

# Kolom yang akan di-load (hanya yang diperlukan)
COLS_TO_LOAD = [
    'Stock Code', 'Company Name', 'Sector', 'Last Trading Date',
    'Close', 'Volume', 'Net Foreign', 'CMF', 'MFI'
]

@st.cache_data(ttl=3600, show_spinner="Memuat data saham...")
def load_data():
    try:
        # Pakai gcsfs untuk baca parquet
        from google.oauth2 import service_account
        from gcsfs import GCSFileSystem
            
        creds = service_account.Credentials.from_service_account_info(
            st.secrets["gcp_service_account"]
        )
        fs = GCSFileSystem(project="stock-analysis-461503", token=creds)
        with fs.open(GCS_PATH) as f:
            return pd.read_parquet(f, columns=COLS_TO_LOAD)
    except Exception as e:
        st.error(f"ERROR: {str(e)}")
        return pd.DataFrame()

# UI Minimalis
st.set_page_config(layout="wide", page_title="🚀 Turbo Saham IDX")
st.title("💨 ULTRA-FAST SAHAM INDONESIA DASHBOARD")

# Load data
with st.spinner('Memuat data dari GCS...'):
    df = load_data()
    
    if df.empty:
        st.error("Data tidak berhasil dimuat!")
        st.stop()

# Pre-cache daftar saham
all_stocks = df['Stock Code'].unique().tolist()

# Sidebar
with st.sidebar:
    st.header("⚙️ KONTROL UTAMA")
    selected_stock = st.selectbox(
        "PILIH SAHAM", 
        all_stocks,
        index=0
    )
    
    # Date range picker
    min_date = df['Last Trading Date'].min().date()
    max_date = df['Last Trading Date'].max().date()
    start_date, end_date = st.date_input(
        "RENTANG WAKTU",
        value=[min_date, max_date],
        min_value=min_date,
        max_value=max_date
    )

# Filter data berdasarkan saham & tanggal
stock_df = df[
    (df['Stock Code'] == selected_stock) &
    (df['Last Trading Date'].between(pd.Timestamp(start_date), pd.Timestamp(end_date))
].sort_values('Last Trading Date')

# Tampilkan visualisasi
if not stock_df.empty:
    # Tab view
    tab1, tab2 = st.tabs(["📈 Chart", "🧾 Data"])
    
    with tab1:
        # Price Chart
        fig1 = px.line(stock_df, x='Last Trading Date', y='Close', 
                      title=f"<b>{selected_stock} - Price Movement</b>")
        st.plotly_chart(fig1, use_container_width=True)
        
        # CMF & MFI
        col1, col2 = st.columns(2)
        with col1:
            if 'CMF' in stock_df.columns and not stock_df['CMF'].isna().all():
                fig2 = px.line(stock_df, x='Last Trading Date', y='CMF', 
                              title="<b>Chaikin Money Flow</b>")
                fig2.add_hline(y=0, line_dash="dash", line_color="red")
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.warning("Data CMF tidak tersedia")
        
        with col2:
            if 'MFI' in stock_df.columns and not stock_df['MFI'].isna().all():
                fig3 = px.line(stock_df, x='Last Trading Date', y='MFI', 
                              title="<b>Money Flow Index</b>")
                fig3.add_hrect(y0=0, y1=20, fillcolor="green", opacity=0.2)
                fig3.add_hrect(y0=80, y1=100, fillcolor="red", opacity=0.2)
                st.plotly_chart(fig3, use_container_width=True)
            else:
                st.warning("Data MFI tidak tersedia")
        
        # Net Foreign
        if 'Net Foreign' in stock_df.columns and not stock_df['Net Foreign'].isna().all():
            fig4 = px.bar(stock_df, x='Last Trading Date', y='Net Foreign',
                         color='Net Foreign', color_continuous_scale='RdYlGn',
                         title="<b>Net Foreign Flow</b>")
            st.plotly_chart(fig4, use_container_width=True)
        else:
            st.warning("Data Net Foreign tidak tersedia")
    
    with tab2:
        st.dataframe(stock_df.sort_values('Last Trading Date', ascending=False))
else:
    st.warning("Data tidak ditemukan untuk filter ini")

# Footer
st.caption(f"⚡ Ultra-Fast Mode | Data: {len(df):,} baris | Terakhir update: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
