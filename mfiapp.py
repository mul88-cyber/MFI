import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io # Untuk debugging df.info()

# --- Fungsi untuk menghitung Money Flow Index (MFI) ---
def calculate_mfi(df, period=14):
    # Pastikan kolom yang dibutuhkan ada setelah rename
    required_cols = ['High', 'Low', 'Close', 'Volume']
    for col in required_cols:
        if col not in df.columns:
            st.error(f"Error: Kolom '{col}' tidak ditemukan setelah proses pembersihan nama. Pastikan data Anda lengkap.")
            return pd.DataFrame() # Kembalikan DataFrame kosong jika kolom tidak lengkap

    df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
    
    # Calculate Raw Money Flow
    df['Raw_Money_Flow'] = df['Typical_Price'] * df['Volume']
    
    # Calculate Money Flow (Positive and Negative)
    df['Positive_MF'] = 0.0
    df['Negative_MF'] = 0.0

    # Menggunakan .loc untuk menghindari SettingWithCopyWarning dan performa lebih baik
    # Iterasi dari indeks 1 karena membandingkan dengan Typical_Price sebelumnya
    for i in range(1, len(df)):
        if df['Typical_Price'].iloc[i] > df['Typical_Price'].iloc[i-1]:
            df.loc[df.index[i], 'Positive_MF'] = df['Raw_Money_Flow'].iloc[i]
        elif df['Typical_Price'].iloc[i] < df['Typical_Price'].iloc[i-1]:
            df.loc[df.index[i], 'Negative_MF'] = df['Raw_Money_Flow'].iloc[i]
            
    # Calculate Money Flow Ratio
    df['Positive_MF_Sum'] = df['Positive_MF'].rolling(window=period).sum()
    df['Negative_MF_Sum'] = df['Negative_MF'].rolling(window=period).sum()
    
    # Menangani kasus pembagian oleh nol jika Negative_MF_Sum adalah 0
    # Menggunakan np.inf untuk menghindari warning dan hasil yang benar saat dibagi 0
    df['Money_Flow_Ratio'] = df['Positive_MF_Sum'] / df['Negative_MF_Sum'].replace(0, pd.NA) # pd.NA akan menghasilkan NaN
    
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
        
        # --- Membersihkan nama kolom: menghapus spasi ekstra ---
        df.columns = df.columns.str.strip() 

        # --- Debugging: Tampilkan kolom yang terdeteksi setelah load CSV ---
        # st.write("Kolom yang terdeteksi di CSV setelah di load:", df.columns.tolist())
        
        # Tentukan kolom tanggal yang benar
        date_column_name_in_csv = None
        if 'Last trading Date' in df.columns:
            date_column_name_in_csv = 'Last trading Date'
        elif 'Date' in df.columns: 
            date_column_name_in_csv = 'Date'
        else:
            raise ValueError("Kolom tanggal ('Last trading Date' atau 'Date') tidak ditemukan di CSV.")

        df[date_column_name_in_csv] = pd.to_datetime(df[date_column_name_in_csv], errors='coerce')
        df.dropna(subset=[date_column_name_in_csv], inplace=True) # Hapus baris dengan tanggal yang tidak valid
        df.rename(columns={date_column_name_in_csv: 'Date'}, inplace=True) # Ubah nama kolom menjadi 'Date'
        df.set_index('Date', inplace=True)
        
        # --- Update nama kolom OHLC sesuai informasi baru ---
        # Asumsi: jika ada 'Open Price', maka High/Low/Close juga mungkin punya ' Price'
        # Kita akan cek dan rename jika ditemukan
        column_mapping = {
            'Open Price': 'Open',
            'High Price': 'High',
            'Low Price': 'Low',
            'Close Price': 'Close',
            'Foreign_Buy': 'Foreign_Buy', # Pastikan ini tetap sama
            'Foreign_Sell': 'Foreign_Sell', # Pastikan ini tetap sama
            'Stock Code': 'Stock Code' # Pastikan ini tetap sama
        }
        
        for old_name, new_name in column_mapping.items():
            if old_name in df.columns and old_name != new_name:
                df.rename(columns={old_name: new_name}, inplace=True)
            # Jika nama lama sudah tidak ada tapi nama baru tidak ada, kita bisa raise error
            # Namun, karena kita akan cek di numeric_cols, ini tidak terlalu krusial di sini.

        # Pastikan kolom numerik adalah numerik
        # List ini sekarang menggunakan nama standar 'Open', 'High', dll. setelah proses rename di atas
        numeric_cols_to_convert = ['Open', 'High', 'Low', 'Close', 'Volume', 'Foreign_Buy', 'Foreign_Sell', 'Freq']
        for col in numeric_cols_to_convert:
            if col in df.columns: # Pastikan kolom ada sebelum mencoba konversi
                df[col] = pd.to_numeric(df[col], errors='coerce')
            # else:
                # Jika Anda ingin tahu jika ada kolom yang hilang setelah rename
                # st.warning(f"Kolom '{col}' tidak ditemukan di DataFrame setelah rename/pemrosesan.") 

        # Drop baris yang memiliki NaN di kolom OHLC dan Volume setelah konversi
        # Ini penting agar perhitungan MFI tidak error
        required_ohlcv = ['Open', 'High', 'Low', 'Close', 'Volume']
        df = df.dropna(subset=[col for col in required_ohlcv if col in df.columns])

        return df 
    
    except Exception as e:
        st.error(f"Gagal memuat data dari GCS: {e}")
        st.info("Pastikan bucket GCS Anda dapat diakses publik, nama file benar, dan format kolom sesuai. Error detail: " + str(e))
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
    
    # Buat list kolom yang benar-benar ada di df_filtered_date
    # Ini penting karena jika ada kolom yang hilang di data asli, plotly tidak akan error
    ohlc_cols = ['Open', 'High', 'Low', 'Close']
    available_ohlc_cols = [col for col in ohlc_cols if col in df_filtered_date.columns]

    if len(available_ohlc_cols) == 4 and 'Volume' in df_filtered_date.columns and 'MFI' in df_filtered_date.columns:
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
    else:
        st.warning("Data OHLC, Volume, atau MFI tidak lengkap untuk menampilkan grafik. Silakan periksa data.")

    # --- Tabel Data Detail ---
    st.write("### Data Detail Harian")
    # Tampilkan kolom yang dijamin ada
    columns_to_display_base = ['Open', 'High', 'Low', 'Close', 'Volume']
    # Tambahkan kolom yang mungkin ada
    optional_cols_to_display = ['Foreign_Buy', 'Foreign_Sell', 'Freq', 'MFI']

    # Filter kolom yang benar-benar ada di DataFrame
    actual_columns_to_display = [col for col in columns_to_display_base if col in df_filtered_date.columns]
    actual_columns_to_display.extend([col for col in optional_cols_to_display if col in df_filtered_date.columns and col not in actual_columns_to_display])

    if actual_columns_to_display:
        st.dataframe(df_filtered_date[actual_columns_to_display].style.format({
            'Open': "{:.2f}", 
            'High': "{:.2f}", 
            'Low': "{:.2f}", 
            'Close': "{:.2f}",
            'MFI': "{:.2f}",
            'Volume': "{:,}", # Format volume dengan koma
            'Foreign_Buy': "{:,}",
            'Foreign_Sell': "{:,}",
            'Freq': "{:,}"
        }))
    else:
        st.info("Tidak ada kolom yang valid untuk ditampilkan dalam tabel data detail.")

else:
    st.warning("Tidak ada data yang tersedia untuk ditampilkan berdasarkan pilihan Anda.")


# --- Top 25 Stock Picks ---
st.markdown("---") # Garis pemisah
st.header("🏆 Top 25 Stock Picks (Berdasarkan Volume Harian Terbaru)")

# Pastikan 'Stock Code', 'Volume', 'Foreign_Buy', 'Foreign_Sell' dan 'Close' ada di df_full
if 'Stock Code' in df_full.columns and 'Volume' in df_full.columns and \
   'Foreign_Buy' in df_full.columns and 'Foreign_Sell' in df_full.columns and \
   'Close' in df_full.columns and not df_full.empty:
    
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
    st.info("Kolom penting ('Stock Code', 'Volume', 'Foreign_Buy', 'Foreign_Sell', 'Close') tidak ditemukan atau data kosong, tidak dapat menampilkan Top 25 Stock Picks. Periksa kembali nama kolom di CSV Anda.")
