import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io

# --- Fungsi untuk menghitung Money Flow Index (MFI) ---
def calculate_mfi(df, period=14):
    df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
    
    # Calculate Raw Money Flow
    df['Raw_Money_Flow'] = df['Typical_Price'] * df['Volume']
    
    # Calculate Money Flow (Positive and Negative)
    df['Positive_MF'] = 0.0
    df['Negative_MF'] = 0.0

    # Menggunakan .loc untuk menghindari SettingWithCopyWarning dan performa lebih baik
    for i in range(1, len(df)):
        if df['Typical_Price'].iloc[i] > df['Typical_Price'].iloc[i-1]:
            df.loc[df.index[i], 'Positive_MF'] = df['Raw_Money_Flow'].iloc[i]
        elif df['Typical_Price'].iloc[i] < df['Typical_Price'].iloc[i-1]:
            df.loc[df.index[i], 'Negative_MF'] = df['Raw_Money_Flow'].iloc[i]
            
    # Calculate Money Flow Ratio
    df['Positive_MF_Sum'] = df['Positive_MF'].rolling(window=period).sum()
    df['Negative_MF_Sum'] = df['Negative_MF'].rolling(window=period).sum()
    
    # Menangani kasus pembagian oleh nol jika Negative_MF_Sum adalah 0
    df['Money_Flow_Ratio'] = df['Positive_MF_Sum'] / df['Negative_MF_Sum'].replace(0, pd.NA)
    
    # Calculate MFI
    df['MFI'] = 100 - (100 / (1 + df['Money_Flow_Ratio']))
    
    return df.dropna(subset=['MFI']) # Drop NaN values created by rolling window, khusus MFI

# --- Konfigurasi Halaman Streamlit ---
st.set_page_config(
    page_title="Dashboard Saham IDX - Money Flow",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📊 Dashboard Saham IDX")
st.subheader("Analisis Harga, Volume, dan Money Flow")

# --- Muat Data dari GCS ---
GCS_BUCKET_NAME = 'stock-csvku'
GCS_FILE_NAME = 'hasil_gabungan.csv'
GCS_PATH = f'gs://{GCS_BUCKET_NAME}/{GCS_FILE_NAME}'

@st.cache_data # Cache data agar tidak diunduh berulang kali
def load_data_from_gcs(path):
    try:
        df = pd.read_csv(path)
        # Menggunakan nama kolom yang baru sesuai info user
        df['Last trading Date'] = pd.to_datetime(df['Last trading Date'])
        df.rename(columns={'Last Trading Date': 'Date'}, inplace=True) # Ubah nama kolom untuk konsistensi
        df.set_index('Date', inplace=True)
        # Pastikan kolom numerik adalah numerik
        numeric_cols = ['Open', 'High', 'Low', 'Close', 'Volume', 'Foreign_Buy', 'Foreign_Sell', 'Freq']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        return df.dropna(subset=['Open', 'High', 'Low', 'Close', 'Volume']) # Drop baris dengan NaN di kolom penting
    except Exception as e:
        st.error(f"Gagal memuat data dari GCS: {e}")
        st.info("Pastikan bucket GCS Anda dapat diakses publik dan nama file benar.")
        return pd.DataFrame() # Kembalikan DataFrame kosong jika gagal

df_full = load_data_from_gcs(GCS_PATH)

if df_full.empty:
    st.stop() # Hentikan eksekusi jika data gagal dimuat

# --- Sidebar untuk Pilihan Saham dan Filter Tanggal ---
st.sidebar.header("Pilih Saham & Filter Data")

# Pastikan 'Stock Code' ada sebelum digunakan
if 'Stock Code' in df_full.columns:
    stock_codes = sorted(df_full['Stock Code'].unique())
    selected_stock = st.sidebar.selectbox("Pilih Kode Saham", stock_codes)
    df_selected_stock = df_full[df_full['Stock Code'] == selected_stock].copy()
else:
    st.warning("Kolom 'Stock Code' tidak ditemukan. Menampilkan data gabungan.")
    df_selected_stock = df_full.copy()
    
# Hitung MFI untuk saham yang dipilih
if not df_selected_stock.empty:
    df_processed = calculate_mfi(df_selected_stock.copy())
else:
    st.warning("Tidak ada data untuk saham yang dipilih.")
    df_processed = pd.DataFrame()


# Filter Tanggal
if not df_processed.empty:
    min_date_data = df_processed.index.min().date()
    max_date_data = df_processed.index.max().date()
    
    date_range = st.sidebar.date_input(
        "Pilih Rentang Tanggal",
        value=(min_date_data, max_date_data),
        min_value=min_date_data,
        max_value=max_date_data
    )

    if len(date_range) == 2:
        start_date, end_date = date_range[0], date_range[1]
        df_filtered_date = df_processed[(df_processed.index.date >= start_date) & 
                                        (df_processed.index.date <= end_date)].copy()
    else:
        df_filtered_date = df_processed.copy() # Tampilkan semua jika rentang tidak lengkap
else:
    df_filtered_date = pd.DataFrame()

# --- Main Content ---
if not df_filtered_date.empty:
    st.write(f"### Grafik Harga & Money Flow Index (MFI) untuk {selected_stock if 'Stock Code' in df_full.columns else 'Semua Saham'}")
    
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.1, 
                        row_heights=[0.7, 0.3])

    # Candlestick chart
    fig.add_trace(go.Candlestick(x=df_filtered_date.index,
                                open=df_filtered_date['Open'],
                                high=df_filtered_date['High'],
                                low=df_filtered_date['Low'],
                                close=df_filtered_date['Close'],
                                name='Harga'), row=1, col=1)

    # Volume bar chart
    fig.add_trace(go.Bar(x=df_filtered_date.index, y=df_filtered_date['Volume'], 
                            name='Volume', marker_color='grey', opacity=0.5), row=1, col=1)

    # MFI chart
    fig.add_trace(go.Scatter(x=df_filtered_date.index, y=df_filtered_date['MFI'], 
                            mode='lines', name='Money Flow Index (MFI)', 
                            line=dict(color='purple', width=2)), row=2, col=1)
    
    # MFI Overbought/Oversold levels
    fig.add_hline(y=80, line_dash="dash", line_color="red", annotation_text="Overbought (80)", annotation_position="top left", row=2, col=1)
    fig.add_hline(y=20, line_dash="dash", line_color="green", annotation_text="Oversold (20)", annotation_position="bottom left", row=2, col=1)


    fig.update_layout(
        xaxis_rangeslider_visible=False,
        title_text=f'Data Harga dan MFI Saham {selected_stock if "Stock Code" in df_full.columns else ""}',
        height=700,
        hovermode="x unified"
    )

    fig.update_yaxes(title_text="Harga / Volume", row=1, col=1)
    fig.update_yaxes(title_text="MFI", range=[0, 100], row=2, col=1)
    
    st.plotly_chart(fig, use_container_width=True)

    # --- Tabel Data Detail ---
    st.write("### Data Detail Harian")
    columns_to_display = ['Open', 'High', 'Low', 'Close', 'Volume', 'Foreign_Buy', 'Foreign_Sell', 'Freq', 'MFI']
    actual_columns_to_display = [col for col in columns_to_display if col in df_filtered_date.columns]

    st.dataframe(df_filtered_date[actual_columns_to_display].style.format({
        'Open': "{:.2f}", 
        'High': "{:.2f}", 
        'Low': "{:.2f}", 
        'Close': "{:.2f}",
        'MFI': "{:.2f}"
    }))

else:
    st.warning("Tidak ada data yang tersedia untuk ditampilkan berdasarkan pilihan Anda.")


# --- Top 25 Stock Picks ---
st.markdown("---") # Garis pemisah
st.header("🏆 Top 25 Stock Picks (Berdasarkan Volume Harian Terbaru)")

if 'Stock Code' in df_full.columns and not df_full.empty:
    # Ambil tanggal terakhir yang tersedia di seluruh dataset
    latest_date = df_full.index.max()

    # Filter data untuk tanggal terakhir saja
    df_latest_day = df_full[df_full.index == latest_date].copy()

    if not df_latest_day.empty:
        # Hitung Net Foreign Flow
        df_latest_day['Net_Foreign_Flow'] = df_latest_day['Foreign_Buy'] - df_latest_day['Foreign_Sell']

        # Urutkan berdasarkan Volume (atau metrik lain yang Anda inginkan)
        # dan ambil 25 teratas
        top_25_stocks = df_latest_day.sort_values(by='Volume', ascending=False).head(25)

        # Tampilkan dalam tabel
        st.dataframe(top_25_stocks[['Stock Code', 'Close', 'Volume', 'Net_Foreign_Flow', 'Freq']].style.format({
            'Close': "{:.2f}",
            'Volume': "{:,}",
            'Net_Foreign_Flow': "{:,}",
            'Freq': "{:,}"
        }))
    else:
        st.info("Tidak ada data untuk tanggal terbaru untuk menghitung Top 25 Stock Picks.")
else:
    st.info("Kolom 'Stock Code' tidak ditemukan atau data kosong, tidak dapat menampilkan Top 25 Stock Picks.")
