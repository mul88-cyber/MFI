import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io # Untuk debugging df.info()

# --- Fungsi untuk menghitung Money Flow Index (MFI) ---
def calculate_mfi(df, period=14):
    # Pastikan kolom yang dibutuhkan ada sebelum perhitungan
    # Perhatikan: menggunakan 'Open Price' sesuai update terakhir Anda
    required_ohlcv = ['Open Price', 'High', 'Low', 'Close', 'Volume']
    for col in required_ohlcv:
        if col not in df.columns:
            st.error(f"Error MFI Calc: Kolom '{col}' tidak ditemukan untuk perhitungan MFI.")
            return pd.DataFrame() # Kembalikan DataFrame kosong jika kolom tidak lengkap

    df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
    
    df['Raw_Money_Flow'] = df['Typical_Price'] * df['Volume']
    
    df['Positive_MF'] = 0.0
    df['Negative_MF'] = 0.0

    # Iterasi dari indeks 1 karena membandingkan dengan Typical_Price sebelumnya
    for i in range(1, len(df)):
        if df['Typical_Price'].iloc[i] > df['Typical_Price'].iloc[i-1]:
            df.loc[df.index[i], 'Positive_MF'] = df['Raw_Money_Flow'].iloc[i]
        elif df['Typical_Price'].iloc[i] < df['Typical_Price'].iloc[i-1]:
            df.loc[df.index[i], 'Negative_MF'] = df['Raw_Money_Flow'].iloc[i]
            
    df['Positive_MF_Sum'] = df['Positive_MF'].rolling(window=period).sum()
    df['Negative_MF_Sum'] = df['Negative_MF'].rolling(window=period).sum()
    
    # Menangani kasus pembagian oleh nol jika Negative_MF_Sum adalah 0
    df['Money_Flow_Ratio'] = df['Positive_MF_Sum'] / df['Negative_MF_Sum'].replace(0, pd.NA) 
    
    df['MFI'] = 100 - (100 / (1 + df['Money_Flow_Ratio']))
    
    return df.dropna(subset=['MFI']) 

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

@st.cache_data(show_spinner="Memuat data dari Google Cloud Storage...") # Cache data agar tidak diunduh berulang kali
def load_data_from_gcs(path):
    try:
        df = pd.read_csv(path)
        
        # --- Membersihkan nama kolom: menghapus spasi ekstra ---
        df.columns = df.columns.str.strip() 

        # --- Debugging (Uncomment jika perlu) ---
        # st.sidebar.write("Kolom yang terdeteksi di CSV setelah di load:", df.columns.tolist())
        
        # Tentukan kolom tanggal yang benar
        date_column_name_in_csv = None
        if 'Date' in df.columns: # Sesuai dengan file hasil_gabungan.csv yang diberikan
            date_column_name_in_csv = 'Date'
        elif 'Last Trading Date' in df.columns: # Fallback jika nama kolom berubah di masa depan
            date_column_name_in_csv = 'Last Trading Date'
        else:
            raise ValueError("Kolom tanggal ('Date' atau 'Last Trading Date') tidak ditemukan di CSV.")

        df[date_column_name_in_csv] = pd.to_datetime(df[date_column_name_in_csv], errors='coerce')
        df.dropna(subset=[date_column_name_in_csv], inplace=True) # Hapus baris dengan tanggal yang tidak valid
        df.rename(columns={date_column_name_in_csv: 'Date'}, inplace=True) # Ubah nama kolom menjadi 'Date'
        df.set_index('Date', inplace=True)
        
        # --- Mengkonversi kolom numerik ---
        # Menggunakan nama kolom yang ada di CSV Anda sesuai info terakhir:
        numeric_cols_to_convert = ['Open Price', 'High', 'Low', 'Close', 'Volume', 'Foreign Buy', 'Foreign Sell', 'Frequency'] # Perbaikan: 'Frequency' -> 'Frequency'
        for col in numeric_cols_to_convert:
            if col in df.columns: 
                df[col] = pd.to_numeric(df[col], errors='coerce')
            else:
                st.warning(f"Kolom '{col}' tidak ditemukan di DataFrame. Perhitungan atau tampilan mungkin terpengaruh.") 

        # Drop baris yang memiliki NaN di kolom OHLC dan Volume setelah konversi
        required_ohlcv_for_mfi = ['Open Price', 'High', 'Low', 'Close', 'Volume'] # Menggunakan 'Open Price'
        df = df.dropna(subset=[col for col in required_ohlcv_for_mfi if col in df.columns])

        return df 
    
    except Exception as e:
        st.error(f"Gagal memuat data dari GCS: {e}")
        st.info(f"Pastikan bucket GCS Anda dapat diakses publik, nama file benar, dan format kolom sesuai. Detail: {e}")
        return pd.DataFrame() # Kembalikan DataFrame kosong jika gagal

df_full = load_data_from_gcs(GCS_PATH)

if df_full.empty:
    st.stop() # Hentikan eksekusi jika data gagal dimuat

# --- Definisikan Tab ---
tab1, tab2 = st.tabs(["📈 Analisis Saham Individu", "🏆 Top Stock Picks"])

# --- TAB 1: Analisis Saham Individu ---
with tab1:
    st.header("Analisis Harga & Money Flow Index")

    # --- Sidebar untuk Pilihan Saham dan Filter Tanggal (di dalam tab1) ---
    # Jika 'Stock Code' ada di df_full, tampilkan selectbox
    if 'Stock Code' in df_full.columns:
        stock_codes = sorted(df_full['Stock Code'].unique())
        selected_stock = st.sidebar.selectbox("Pilih Kode Saham", stock_codes, key='stock_select_tab1')
        df_selected_stock = df_full[df_full['Stock Code'] == selected_stock].copy()
    else:
        st.info("Kolom 'Stock Code' tidak ditemukan di data Anda. Menampilkan data saham tunggal yang diunggah.")
        df_selected_stock = df_full.copy() # Asumsi seluruh data adalah untuk 1 saham
        selected_stock = "Data Tunggal" # Label untuk tampilan

    # Hitung MFI untuk saham yang dipilih
    df_processed = pd.DataFrame() # Inisialisasi
    if not df_selected_stock.empty:
        df_processed = calculate_mfi(df_selected_stock.copy())
    
    if df_processed.empty:
        st.warning("Tidak ada data yang cukup atau valid untuk saham yang dipilih guna menghitung MFI dan menampilkan grafik.")
    else:
        # Filter Tanggal
        min_date_data = df_processed.index.min().date()
        max_date_data = df_processed.index.max().date()
        
        date_range = st.sidebar.date_input(
            "Pilih Rentang Tanggal",
            value=(min_date_data, max_date_data),
            min_value=min_date_data,
            max_value=max_date_data,
            key='date_range_tab1'
        )

        if len(date_range) == 2:
            start_date, end_date = date_range[0], date_range[1]
            df_filtered_date = df_processed[(df_processed.index.date >= start_date) & 
                                            (df_processed.index.date <= end_date)].copy()
        else:
            df_filtered_date = df_processed.copy() # Tampilkan semua jika rentang tidak lengkap

        # --- Main Content Grafis & Tabel ---
        if not df_filtered_date.empty:
            st.write(f"#### Grafik Harga & Money Flow Index (MFI) untuk {selected_stock}")
            
            # List kolom OHLC yang akan digunakan di Plotly
            # Perhatikan: Nama kolom di DataFrame adalah 'Open Price', 'High', 'Low', 'Close'
            # Tapi parameter di Plotly adalah 'open', 'high', 'low', 'close'
            ohlc_cols_df = ['Open Price', 'High', 'Low', 'Close'] 
            available_ohlc_cols = [col for col in ohlc_cols_df if col in df_filtered_date.columns]

            if len(available_ohlc_cols) == 4 and 'Volume' in df_filtered_date.columns and 'MFI' in df_filtered_date.columns:
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                    vertical_spacing=0.1, 
                                    row_heights=[0.7, 0.3])

                # Candlestick chart - KOREKSI DI SINI!
                # Nama parameter Plotly adalah 'open', 'high', 'low', 'close'
                fig.add_trace(go.Candlestick(x=df_filtered_date.index,
                                            open=df_filtered_date['Open Price'], # Pastikan ini mengacu ke nama kolom di DF
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
                    title_text=f'Data Harga dan MFI Saham {selected_stock}',
                    height=700,
                    hovermode="x unified"
                )

                fig.update_yaxes(title_text="Harga / Volume", row=1, col=1)
                fig.update_yaxes(title_text="MFI", range=[0, 100], row=2, col=1)
                
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("Data OHLC, Volume, atau MFI tidak lengkap untuk menampilkan grafik. Silakan periksa data.")

            # --- Tabel Data Detail ---
            st.write("#### Data Detail Harian")
            # Menggunakan nama kolom yang ada di DataFrame
            columns_to_display_base = ['Open Price', 'High', 'Low', 'Close', 'Volume']
            optional_cols_to_display = ['Foreign Buy', 'Foreign Sell', 'Frequency', 'MFI'] # Perbaikan: 'Frequency' -> 'Frequency'

            actual_columns_to_display = [col for col in columns_to_display_base if col in df_filtered_date.columns]
            actual_columns_to_display.extend([col for col in optional_cols_to_display if col in df_filtered_date.columns and col not in actual_columns_to_display])

            if actual_columns_to_display:
                st.dataframe(df_filtered_date[actual_columns_to_display].style.format({
                    'Open Price': "{:.2f}", 
                    'High': "{:.2f}", 
                    'Low': "{:.2f}", 
                    'Close': "{:.2f}",
                    'MFI': "{:.2f}",
                    'Volume': "{:,}", 
                    'Foreign Buy': "{:,}",
                    'Foreign Sell': "{:,}",
                    'Frequency': "{:,}" # Perbaikan: 'Frequency' -> 'Frequency'
                }))
            else:
                st.info("Tidak ada kolom yang valid untuk ditampilkan dalam tabel data detail.")

        else:
            st.warning("Tidak ada data yang tersedia untuk ditampilkan berdasarkan rentang tanggal yang dipilih.")


# --- TAB 2: Top Stock Picks ---
with tab2:
    st.header("🏆 Top Stock Picks (Berdasarkan Volume Harian Terbaru)")

    # Pengecekan ketat untuk kolom yang dibutuhkan di sini
    required_top_pick_cols = ['Stock Code', 'Volume', 'Foreign Buy', 'Foreign Sell', 'Close'] # Menggunakan 'Foreign Buy', 'Foreign Sell'
    if all(col in df_full.columns for col in required_top_pick_cols) and not df_full.empty:
        
        # Ambil tanggal terakhir yang tersedia di seluruh dataset
        latest_date = df_full.index.max()

        # Filter data untuk tanggal terakhir saja
        df_latest_day = df_full[df_full.index == latest_date].copy()

        if not df_latest_day.empty:
            # Hitung Net Foreign Flow
            df_latest_day['Net_Foreign_Flow'] = df_latest_day['Foreign Buy'] - df_latest_day['Foreign Sell'] # Menggunakan 'Foreign Buy', 'Foreign Sell'

            # Urutkan berdasarkan Volume (atau metrik lain yang Anda inginkan)
            # dan ambil 25 teratas
            top_25_stocks = df_latest_day.sort_values(by='Volume', ascending=False).head(25)

            st.write(f"Data Top Picks per tanggal **{latest_date.strftime('%Y-%m-%d')}**")
            # Tampilkan dalam tabel
            st.dataframe(top_25_stocks[['Stock Code', 'Close', 'Volume', 'Net_Foreign_Flow', 'Frequency']].style.format({ # Perbaikan: 'Frequency' -> 'Frequency'
                'Close': "{:.2f}",
                'Volume': "{:,}",
                'Net_Foreign_Flow': "{:,}",
                'Frequency': "{:,}" # Perbaikan: 'Frequency' -> 'Frequency'
            }))
        else:
            st.info("Tidak ada data untuk tanggal terbaru untuk menghitung Top Stock Picks.")
    else:
        st.warning(
            "Kolom penting untuk 'Top Stock Picks' tidak ditemukan di data Anda (misalnya 'Stock Code').\n\n"
            "**Untuk mengaktifkan fitur ini, pastikan file CSV Anda berisi data dari banyak saham dan memiliki kolom 'Stock Code' untuk identifikasi saham.**"
        )
        # Menampilkan kolom yang diharapkan vs. yang ditemukan untuk debugging
        st.info("Kolom yang diharapkan: " + ", ".join(required_top_pick_cols) + ". Kolom yang ditemukan: " + ", ".join(df_full.columns.tolist()))
