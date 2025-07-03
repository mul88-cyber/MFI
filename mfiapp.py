import streamlit as st
import pandas as pd
import plotly.express as px
from ta.volume import ChaikinMoneyFlowIndicator, MFIIndicator
import numpy as np
import time

# Konfigurasi
BUCKET_NAME = "stock-csvku"
FILE_NAME = "hasil_gabungan.parquet"  # PAKAI PARQUET!
GCS_PATH = f"gs://{BUCKET_NAME}/{FILE_NAME}"

# Kolom yang akan di-load (MINIMALISIR!)
COLS_TO_LOAD = [
    'Stock Code', 'Last Trading Date', 
    'High', 'Low', 'Close', 'Volume', 'Net Foreign'
]

@st.cache_data(ttl=3600, show_spinner="Memuat data saham...")
def load_data():
    try:
        # Pakai gcsfs untuk baca parquet
        if 'gcp_service_account' in st.secrets:
            from google.oauth2 import service_account
            from gcsfs import GCSFileSystem
            
            creds = service_account.Credentials.from_service_account_info(
                st.secrets["gcp_service_account"]
            )
            fs = GCSFileSystem(project="stock-analysis-461503", token=creds)
            with fs.open(GCS_PATH) as f:
                return pd.read_parquet(f, columns=COLS_TO_LOAD)
        else:
            # Untuk public bucket (tidak disarankan)
            return pd.read_parquet(GCS_PATH, columns=COLS_TO_LOAD)
    except Exception as e:
        st.error(f"ERROR: {str(e)}")
        return pd.DataFrame()

# Fungsi kalkulasi indikator dengan caching
def calculate_indicators(stock_df):
    if len(stock_df) < 20:
        return stock_df.assign(CMF=np.nan, MFI=np.nan)
    
    try:
        # CMF
        cmf_ind = ChaikinMoneyFlowIndicator(
            high=stock_df['High'],
            low=stock_df['Low'],
            close=stock_df['Close'],
            volume=stock_df['Volume'],
            window=20
        )
        stock_df['CMF'] = cmf_ind.chaikin_money_flow()
        
        # MFI
        mfi_ind = MFIIndicator(
            high=stock_df['High'],
            low=stock_df['Low'],
            close=stock_df['Close'],
            volume=stock_df['Volume'],
            window=14
        )
        stock_df['MFI'] = mfi_ind.money_flow_index()
    except Exception as e:
        print(f"Error: {str(e)}")
        stock_df['CMF'] = np.nan
        stock_df['MFI'] = np.nan
    
    return stock_df

# UI Minimalis
st.set_page_config(layout="wide", page_title="🚀 Turbo Saham IDX")
st.title("💨 ULTRA-FAST SAHAM INDONESIA DASHBOARD")

# Load data (dengan progress bar)
with st.spinner('Loading data dari GCS...'):
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

# Hitung indikator JIKA BELUM ADA di cache
if not stock_df.empty:
    cache_key = f"{selected_stock}-{start_date}-{end_date}"
    
    if cache_key not in st.session_state:
        with st.spinner('Menghitung indikator...'):
            processed_df = calculate_indicators(stock_df.copy())
            st.session_state[cache_key] = processed_df
    else:
        processed_df = st.session_state[cache_key]
    
    # Tampilkan dalam tab
    tab1, tab2 = st.tabs(["📈 Chart", "🧾 Data"])
    
    with tab1:
        # Price Chart
        fig1 = px.line(processed_df, x='Last Trading Date', y='Close', 
                      title=f"<b>{selected_stock} - Price Movement</b>")
        st.plotly_chart(fig1, use_container_width=True)
        
        # CMF & MFI
        col1, col2 = st.columns(2)
        with col1:
            if 'CMF' in processed_df:
                fig2 = px.line(processed_df, x='Last Trading Date', y='CMF', 
                              title="<b>Chaikin Money Flow</b>")
                fig2.add_hline(y=0, line_dash="dash", line_color="red")
                st.plotly_chart(fig2, use_container_width=True)
        
        with col2:
            if 'MFI' in processed_df:
                fig3 = px.line(processed_df, x='Last Trading Date', y='MFI', 
                              title="<b>Money Flow Index</b>")
                fig3.add_hrect(y0=0, y1=20, fillcolor="green", opacity=0.2)
                fig3.add_hrect(y0=80, y1=100, fillcolor="red", opacity=0.2)
                st.plotly_chart(fig3, use_container_width=True)
        
        # Net Foreign
        if 'Net Foreign' in processed_df:
            fig4 = px.bar(processed_df, x='Last Trading Date', y='Net Foreign',
                         color='Net Foreign', color_continuous_scale='RdYlGn',
                         title="<b>Net Foreign Flow</b>")
            st.plotly_chart(fig4, use_container_width=True)
    
    with tab2:
        st.dataframe(processed_df.sort_values('Last Trading Date', ascending=False))
else:
    st.warning("Data tidak ditemukan untuk filter ini")

# Footer
st.caption(f"⚡ Turbo Mode | Data: {len(df):,} baris | Terakhir update: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
