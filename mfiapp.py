import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
from io import StringIO
import time

# ========== ⚙️ KONFIGURASI ==========
BUCKET_NAME = "stock-csvku"
FILE_NAME = "hasil_gabungan_final.csv"
GCS_PATH = f"gs://{BUCKET_NAME}/{FILE_NAME}"

# Kolom yang akan di-load
COLS_TO_LOAD = [
    'Stock Code', 'Company Name', 'Sector', 'Last Trading Date',
    'Close', 'Volume', 'Net Foreign', 'CMF', 'MFI'
]

# ========== 📦 FUNGSI LOAD DATA ==========
@st.cache_data(ttl=3600, show_spinner="Memuat data saham...")
def load_data():
    try:
        # Pakai gcsfs untuk baca CSV
        if 'gcp_service_account' in st.secrets:
            from google.oauth2 import service_account
            from gcsfs import GCSFileSystem
            
            # Ambil credentials dari secrets
            creds = service_account.Credentials.from_service_account_info(
                st.secrets["gcp_service_account"]
            )
            fs = GCSFileSystem(project="stock-analysis-461503", token=creds)
            
            # Baca file dari GCS
            with fs.open(GCS_PATH) as f:
                csv_content = f.read().decode('utf-8')
        else:
            # Fallback: Akses langsung (hanya untuk public bucket)
            import requests
            response = requests.get(f"https://storage.googleapis.com/{BUCKET_NAME}/{FILE_NAME}")
            csv_content = response.text
        
        # Baca CSV dengan optimasi memori
        dtype = {
            'Stock Code': 'category',
            'Company Name': 'category',
            'Sector': 'category',
            'Close': 'float32',
            'Volume': 'int32',
            'Net Foreign': 'int32',
            'CMF': 'float32',
            'MFI': 'float32'
        }
        
        return pd.read_csv(
            StringIO(csv_content),
            parse_dates=['Last Trading Date'],
            usecols=COLS_TO_LOAD,
            dtype=dtype
        )
    except Exception as e:
        st.error(f"ERROR: {str(e)}")
        return pd.DataFrame()

# ========== 🚀 DASHBOARD ==========
def main():
    # Konfigurasi halaman
    st.set_page_config(
        layout="wide", 
        page_title="🚀 Turbo Saham IDX",
        page_icon="📈"
    )
    
    st.title("💨 ULTRA-FAST SAHAM INDONESIA DASHBOARD")
    
    # Load data dengan progress bar
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    status_text.text("Memuat data dari GCS...")
    df = load_data()
    progress_bar.progress(40)
    
    if df.empty:
        st.error("Data tidak berhasil dimuat!")
        st.stop()
    
    status_text.text("Mempersiapkan antarmuka...")
    progress_bar.progress(70)
    
    # Cache daftar saham dan tanggal
    if 'all_stocks' not in st.session_state:
        st.session_state.all_stocks = df['Stock Code'].unique().tolist()
        st.session_state.min_date = df['Last Trading Date'].min().date()
        st.session_state.max_date = df['Last Trading Date'].max().date()
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ KONTROL UTAMA")
        selected_stock = st.selectbox(
            "PILIH SAHAM", 
            st.session_state.all_stocks,
            index=0
        )
        
        # Date range picker
        start_date, end_date = st.date_input(
            "RENTANG WAKTU",
            value=[st.session_state.min_date, st.session_state.max_date],
            min_value=st.session_state.min_date,
            max_value=st.session_state.max_date
        )
    
    # Filter data
    stock_df = df[
        (df['Stock Code'] == selected_stock) &
        (df['Last Trading Date'].between(pd.Timestamp(start_date), pd.Timestamp(end_date))
    ].sort_values('Last Trading Date')
    
    # Tampilkan data
    status_text.text("Menyiapkan visualisasi...")
    progress_bar.progress(90)
    
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
    
    progress_bar.progress(100)
    time.sleep(0.5)
    progress_bar.empty()
    status_text.empty()
    
    # Footer
    st.caption(f"⚡ Final Version | Data: {len(df):,} baris | Terakhir update: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")

if __name__ == "__main__":
    main()
