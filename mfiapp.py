import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
from google.oauth2 import service_account
from gcsfs import GCSFileSystem
from ta.volume import ChaikinMoneyFlowIndicator, MFIIndicator

# Load GCS credentials from Streamlit secrets
creds = service_account.Credentials.from_service_account_info(
    st.secrets["gcp_service_account"]
)

@st.cache_data(ttl=3600)  # Cache 1 jam
def load_data():
    fs = GCSFileSystem(project="stock-analysis-461503", token=creds)
    with fs.open("stock-csvku/hasil_gabungan_ori.csv") as f:
        return pd.read_csv(f)

# Load data
df = load_data()

# Preprocessing
df['Last Trading Date'] = pd.to_datetime(df['Last Trading Date'])
df['Net Foreign'] = df['Foreign Buy'] - df['Foreign Sell']

# Calculate indicators
def calculate_indicators(group):
    group = group.sort_values('Last Trading Date')
    high, low, close, volume = group['High'], group['Low'], group['Close'], group['Volume']
    
    # CMF
    cmf = ChaikinMoneyFlowIndicator(high, low, close, volume, window=20)
    group['CMF'] = cmf.chaikin_money_flow()
    
    # MFI
    mfi = MFIIndicator(high, low, close, volume, window=14)
    group['MFI'] = mfi.money_flow_index()
    
    return group

df = df.groupby('Stock Code').apply(calculate_indicators)

# Streamlit UI
st.set_page_config(
    layout="wide", 
    page_title="💰 IDX Money Flow Dashboard",
    page_icon="📈"
)

st.title("🔥 REAL-TIME SAHAM INDONESIA MONEY FLOW")
st.write(f"Data Terakhir: {df['Last Trading Date'].max().strftime('%d %B %Y')}")

# Sidebar
st.sidebar.header("KONTROL ANALISIS")
selected_stock = st.sidebar.selectbox(
    "PILIH KODE SAHAM", 
    df['Stock Code'].unique(),
    index=0
)

selected_sector = st.sidebar.multiselect(
    "FILTER SEKTOR", 
    df['Sector'].unique(),
    default=df['Sector'].unique()
)

date_range = st.sidebar.date_input(
    "RENTANG WAKTU",
    value=[df['Last Trading Date'].min(), df['Last Trading Date'].max()],
    min_value=df['Last Trading Date'].min(),
    max_value=df['Last Trading Date'].max()
)

# Filter data
filtered_df = df[
    (df['Stock Code'] == selected_stock) &
    (df['Sector'].isin(selected_sector)) &
    (df['Last Trading Date'] >= pd.to_datetime(date_range[0])) &
    (df['Last Trading Date'] <= pd.to_datetime(date_range[1]))
]

# Tabs
tab1, tab2, tab3 = st.tabs(["CHART SAHAM", "MONEY FLOW", "ANALISIS SEKTOR"])

with tab1:
    st.header(f"PERGERAKAN HARGA: {selected_stock}")
    fig_price = px.line(
        filtered_df, 
        x='Last Trading Date', 
        y='Close',
        color_discrete_sequence=['#00cc96']
    )
    st.plotly_chart(fig_price, use_container_width=True)
    
    st.header("VOLUME PERDAGANGAN")
    fig_vol = px.bar(
        filtered_df, 
        x='Last Trading Date', 
        y='Volume',
        color='Close',
        color_continuous_scale='blues'
    )
    st.plotly_chart(fig_vol, use_container_width=True)

with tab2:
    col1, col2 = st.columns(2)
    
    with col1:
        st.header("CHAINKIN MONEY FLOW (CMF)")
        fig_cmf = px.area(
            filtered_df, 
            x='Last Trading Date', 
            y='CMF',
            color_discrete_sequence=['#ff7f0e']
        )
        fig_cmf.add_hline(y=0, line_dash="dash", line_color="red")
        st.plotly_chart(fig_cmf, use_container_width=True)
        
    with col2:
        st.header("MONEY FLOW INDEX (MFI)")
        fig_mfi = px.line(
            filtered_df, 
            x='Last Trading Date', 
            y='MFI',
            color_discrete_sequence=['#1f77b4']
        )
        fig_mfi.add_hrect(y0=0, y1=20, fillcolor="green", opacity=0.2)
        fig_mfi.add_hrect(y0=80, y1=100, fillcolor="red", opacity=0.2)
        st.plotly_chart(fig_mfi, use_container_width=True)
    
    st.header("NET FOREIGN FLOW")
    fig_foreign = px.bar(
        filtered_df, 
        x='Last Trading Date', 
        y='Net Foreign',
        color='Net Foreign',
        color_continuous_scale='RdYlGn'
    )
    st.plotly_chart(fig_foreign, use_container_width=True)

with tab3:
    st.header("PERBANDINGAN SEKTOR")
    
    sector_df = df[df['Sector'].isin(selected_sector)]
    sector_summary = sector_df.groupby('Sector').agg(
        Avg_CMF=('CMF', 'mean'),
        Total_Net_Foreign=('Net Foreign', 'sum')
    ).reset_index()
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("RATA-RATA CMF")
        fig_sector_cmf = px.bar(
            sector_summary,
            x='Sector',
            y='Avg_CMF',
            color='Avg_CMF',
            color_continuous_scale='tealrose'
        )
        st.plotly_chart(fig_sector_cmf, use_container_width=True)
        
    with col2:
        st.subheader("ALIRAN ASING NET")
        fig_sector_foreign = px.treemap(
            sector_summary,
            path=['Sector'],
            values='Total_Net_Foreign',
            color='Total_Net_Foreign',
            color_continuous_scale='RdYlGn'
        )
        st.plotly_chart(fig_sector_foreign, use_container_width=True)

# Data preview
st.header("DATA HISTORIS")
st.dataframe(
    filtered_df.sort_values('Last Trading Date', ascending=False),
    height=300,
    hide_index=True
)

# Footer
st.caption("© 2025 IDX Money Flow Dashboard | Dibuat dengan Streamlit")
