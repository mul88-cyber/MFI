import streamlit as st
import pandas as pd
import plotly.express as px
from ta.volume import ChaikinMoneyFlowIndicator, MFIIndicator
import numpy as np

# Konfigurasi
BUCKET_NAME = "stock-csvku"
FILE_NAME = "hasil_gabungan_plus_netforeign.csv"  # File baru
GCS_PATH = f"gs://{BUCKET_NAME}/{FILE_NAME}"

@st.cache_data(ttl=3600)
def load_data():
    # Pakai gcsfs jika ada secrets, atau akses langsung jika public
    if 'gcp_service_account' in st.secrets:
        from google.oauth2 import service_account
        from gcsfs import GCSFileSystem
        
        creds = service_account.Credentials.from_service_account_info(
            st.secrets["gcp_service_account"]
        )
        fs = GCSFileSystem(project="stock-analysis-461503", token=creds)
        with fs.open(GCS_PATH) as f:
            return pd.read_csv(f, parse_dates=['Last Trading Date'])
    else:
        return pd.read_csv(GCS_PATH, parse_dates=['Last Trading Date'])

# Fungsi kalkulasi indikator untuk SATU SAHAM
def calculate_indicators_for_stock(stock_df):
    if len(stock_df) < 20:
        stock_df['CMF'] = np.nan
        stock_df['MFI'] = np.nan
        return stock_df
    
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
    except:
        stock_df['CMF'] = np.nan
        stock_df['MFI'] = np.nan
    
    return stock_df

# UI
st.set_page_config(layout="wide")
st.title("📊 Dashboard Money Flow Saham Indonesia")

# Load data (hanya kolom yang diperlukan)
cols_to_load = [
    'Stock Code', 'Company Name', 'Sector', 'Last Trading Date',
    'Open Price', 'High', 'Low', 'Close', 'Volume', 'Net Foreign'
]

try:
    df = load_data()
    # Pastikan kolom ada sebelum memfilter
    available_cols = [col for col in cols_to_load if col in df.columns]
    df = df[available_cols]
except Exception as e:
    st.error(f"Gagal memuat data: {str(e)}")
    st.stop()

# Sidebar
st.sidebar.header("Kontrol Analisis")
selected_stock = st.sidebar.selectbox(
    "Pilih Saham", 
    df['Stock Code'].unique(),
    index=0
)

# Filter data untuk saham yang dipilih
stock_df = df[df['Stock Code'] == selected_stock].copy().sort_values('Last Trading Date')

# Hitung indikator hanya untuk saham ini
if len(stock_df) > 0:
    stock_df = calculate_indicators_for_stock(stock_df)

# Tampilkan visualisasi
if not stock_df.empty:
    st.subheader(f"Performa Saham: {selected_stock}")
    
    # Tab view
    tab1, tab2, tab3 = st.tabs(["Harga & Volume", "Money Flow", "Net Foreign"])
    
    with tab1:
        fig1 = px.line(stock_df, x='Last Trading Date', y='Close', title="Perubahan Harga")
        st.plotly_chart(fig1, use_container_width=True)
        
        fig2 = px.bar(stock_df, x='Last Trading Date', y='Volume', title="Volume Perdagangan")
        st.plotly_chart(fig2, use_container_width=True)
    
    with tab2:
        if 'CMF' in stock_df.columns:
            fig3 = px.line(stock_df, x='Last Trading Date', y='CMF', title="Chaikin Money Flow (CMF)")
            fig3.add_hline(y=0, line_dash="dash", line_color="red")
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.warning("Kolom CMF tidak tersedia")
            
        if 'MFI' in stock_df.columns:
            fig4 = px.line(stock_df, x='Last Trading Date', y='MFI', title="Money Flow Index (MFI)")
            fig4.add_hline(y=20, line_dash="dash", line_color="green")
            fig4.add_hline(y=80, line_dash="dash", line_color="red")
            st.plotly_chart(fig4, use_container_width=True)
        else:
            st.warning("Kolom MFI tidak tersedia")
    
    with tab3:
        if 'Net Foreign' in stock_df.columns:
            fig5 = px.bar(stock_df, x='Last Trading Date', y='Net Foreign', 
                         color='Net Foreign', color_continuous_scale='RdYlGn',
                         title="Net Foreign Flow")
            st.plotly_chart(fig5, use_container_width=True)
        else:
            st.warning("Kolom Net Foreign tidak tersedia")
    
    # Tampilkan data
    st.subheader("Data Historis")
    st.dataframe(stock_df.sort_values('Last Trading Date', ascending=False))
else:
    st.warning(f"Tidak ditemukan data untuk saham {selected_stock}")

# Footer
st.caption("© 2025 Analisis Saham Indonesia | Data terakhir: " + 
          pd.Timestamp.now().strftime("%Y-%m-%d"))
