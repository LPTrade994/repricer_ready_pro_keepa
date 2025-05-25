import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode
import pandas as pd
import logging
from logging.handlers import TimedRotatingFileHandler
import yaml
from pathlib import Path
from io import BytesIO

from services import io_layer, pricing, mapping

# --- Page Configuration ---
st.set_page_config(page_title="Repricer Ready Pro + Keepa", layout="wide")

# --- Logging Setup ---
LOG_FILE = "repricer.log"
logger = logging.getLogger("RepricerApp")
logger.setLevel(logging.INFO)
if not logger.handlers:
    fh = TimedRotatingFileHandler(LOG_FILE, when="W0", interval=1, backupCount=4, encoding='utf-8')
    fh.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

# --- Configuration Loading ---
def load_app_config() -> dict:
    try:
        with open(Path(__file__).parent / "config/amazon_fees.yml", "r") as f:
            config = yaml.safe_load(f)
        logger.info("Configuration loaded successfully.")
        return config
    except Exception as e:
        st.error(f"Error loading configuration: {e}")
        logger.error(f"Error loading configuration: {e}")
        return {"default_fee_pct": 15}

app_config = load_app_config()

# --- Session State Initialization ---
if 'processed_df' not in st.session_state:
    st.session_state.processed_df = None
if 'original_amazon_columns' not in st.session_state:
    st.session_state.original_amazon_columns = []
if 'original_amazon_dtypes' not in st.session_state:
    st.session_state.original_amazon_dtypes = {}
if 'amazon_filename' not in st.session_state:
    st.session_state.amazon_filename = "ready_pro_export.csv"
if 'last_fee_pct' not in st.session_state:
    st.session_state.last_fee_pct = app_config.get('default_fee_pct', 15)
if 'asins_for_keepa_search' not in st.session_state:
    st.session_state.asins_for_keepa_search = None
if 'amazon_df_loaded' not in st.session_state:
    st.session_state.amazon_df_loaded = None
if 'last_uploaded_amazon_file_name' not in st.session_state:
    st.session_state.last_uploaded_amazon_file_name = None

# --- UI Elements ---
st.title("🏷️ Repricer Ready Pro + Keepa")

with st.sidebar:
    st.header("📂 Caricamento File")
    
    uploaded_amazon_file = st.file_uploader("1. Carica Inserzioni Amazon.CSV", type=["csv"], key="amazon_file_uploader")
    
    asin_extraction_placeholder = st.empty()

    # Modificato per accettare CSV per Keepa
    uploaded_keepa_files = st.file_uploader(
        "2. Carica File Keepa (CSV o XLSX, anche multipli)", 
        type=["csv", "xlsx"], # Accetta entrambi i formati
        accept_multiple_files=True,
        key="keepa_files_uploader"
    )

    st.header("⚙️ Impostazioni Globali")
    amazon_fee_pct_slider = st.slider(
        "Commissione Amazon (%)", 0, 100, 
        value=st.session_state.last_fee_pct, 
        key="amazon_fee_pct_slider_key"
    )
    st.session_state.last_fee_pct = amazon_fee_pct_slider

    process_button = st.button(
        "🔄 Elabora Dati Principali", 
        disabled=not (uploaded_amazon_file and uploaded_keepa_files)
    )

if uploaded_amazon_file:
    if st.session_state.last_uploaded_amazon_file_name != uploaded_amazon_file.name or st.session_state.asins_for_keepa_search is None:
        try:
            logger.info(f"Loading Amazon CSV '{uploaded_amazon_file.name}' for ASIN extraction...")
            amazon_file_bytes_copy = BytesIO(uploaded_amazon_file.getvalue())
            
            temp_amazon_df_for_asins, original_cols_temp, original_dtypes_temp = io_layer.load_amazon_csv(amazon_file_bytes_copy)
            
            st.session_state.amazon_df_loaded = temp_amazon_df_for_asins.copy()
            st.session_state.amazon_filename = uploaded_amazon_file.name
            st.session_state.original_amazon_columns = original_cols_temp
            st.session_state.original_amazon_dtypes = original_dtypes_temp

            st.session_state.asins_for_keepa_search = io_layer.extract_asins_for_keepa_search(temp_amazon_df_for_asins)
            st.session_state.last_uploaded_amazon_file_name = uploaded_amazon_file.name
            logger.info("ASINs extracted for Keepa search.")
        except io_layer.InvalidFileFormatError as e:
            asin_extraction_placeholder.error(f"Errore formato file Amazon: {e}")
            logger.error(f"ASIN Extraction - InvalidFileFormatError: {e}")
            st.session_state.asins_for_keepa_search = None
            st.session_state.amazon_df_loaded = None
            st.session_state.last_uploaded_amazon_file_name = None
        except Exception as e:
            asin_extraction_placeholder.error(f"Errore estrazione ASIN: {e}")
            logger.error(f"ASIN Extraction - Processing error: {e}", exc_info=True)
            st.session_state.asins_for_keepa_search = None
            st.session_state.amazon_df_loaded = None
            st.session_state.last_uploaded_amazon_file_name = None
    
    if st.session_state.asins_for_keepa_search:
        with asin_extraction_placeholder.container():
            st.subheader("📋 ASIN per Ricerca Keepa")
            st.caption("Copia gli ASIN per ogni paese e incollali nella ricerca Bulk ASIN di Keepa.")
            if not st.session_state.asins_for_keepa_search:
                 st.info("Nessun ASIN trovato o mappato correttamente.")
            for locale_code, asins_str in sorted(st.session_state.asins_for_keepa_search.items()):
                num_asins = asins_str.count('\n') + 1 if asins_str else 0
                if num_asins > 0:
                    expander_title = f"{locale_code.upper()} ({mapping.LOCALE_TO_SITO_MAP.get(locale_code, locale_code)}) - {num_asins} ASIN"
                    with st.expander(expander_title):
                        st.code(asins_str, language=None)
            st.markdown("---")
    elif st.session_state.amazon_df_loaded is not None and not st.session_state.asins_for_keepa_search:
         with asin_extraction_placeholder.container():
            st.warning("File Amazon caricato, ma nessun ASIN è stato estratto o mappato per la ricerca Keepa. Verifica il contenuto del file e la mappatura dei 'Sito'.")
            st.markdown("---")

if process_button and uploaded_amazon_file and uploaded_keepa_files:
    try:
        logger.info("Starting main data processing.")
        
        if st.session_state.amazon_df_loaded is not None and st.session_state.amazon_filename == uploaded_amazon_file.name:
            amazon_df = st.session_state.amazon_df_loaded.copy()
            original_cols = st.session_state.original_amazon_columns
            original_dtypes = st.session_state.original_amazon_dtypes
            logger.info("Using pre-loaded Amazon DataFrame for main processing.")
        else:
            logger.info("Reloading Amazon CSV for main processing.")
            amazon_file_bytes_main = BytesIO(uploaded_amazon_file.getvalue())
            amazon_df, original_cols, original_dtypes = io_layer.load_amazon_csv(amazon_file_bytes_main)
            st.session_state.original_amazon_columns = original_cols
            st.session_state.original_amazon_dtypes = original_dtypes
            st.session_state.amazon_filename = uploaded_amazon_file.name
        
        logger.info(f"Amazon CSV for main grid: {len(amazon_df)} rows.")

        all_keepa_dataframes = []
        valid_keepa_files_count = 0
        for keepa_file_single in uploaded_keepa_files:
            try:
                logger.info(f"Loading Keepa file: {keepa_file_single.name}")
                # Determina il tipo di file e chiama la funzione di caricamento appropriata
                if keepa_file_single.name.lower().endswith(".csv"):
                    df_single_keepa = io_layer.load_keepa_csv(keepa_file_single)
                elif keepa_file_single.name.lower().endswith(".xlsx"):
                    df_single_keepa = io_layer.load_keepa_xlsx(keepa_file_single)
                else:
                    st.warning(f"Formato file Keepa non supportato per '{keepa_file_single.name}'. Ignorato.")
                    logger.warning(f"Unsupported Keepa file format for '{keepa_file_single.name}'. Skipped.")
                    continue # Salta al prossimo file
                
                all_keepa_dataframes.append(df_single_keepa)
                valid_keepa_files_count += 1
            except io_layer.InvalidFileFormatError as e_keepa:
                st.warning(f"File Keepa '{keepa_file_single.name}' ignorato: {e_keepa}")
                logger.warning(f"InvalidFileFormatError in Keepa file '{keepa_file_single.name}', skipping: {e_keepa}")
            except Exception as e_general_keepa:
                st.error(f"Errore critico nel caricare il file Keepa '{keepa_file_single.name}': {e_general_keepa}")
                logger.error(f"Critical error loading Keepa file '{keepa_file_single.name}': {e_general_keepa}", exc_info=True)
        
        if not all_keepa_dataframes:
            st.error("Nessun file Keepa valido è stato caricato o processato. Impossibile continuare.")
            logger.error("No valid Keepa files were loaded. Aborting main processing.")
            st.session_state.processed_df = None
            st.stop()

        keepa_df_combined = pd.concat(all_keepa_dataframes, ignore_index=True)
        # Usa 'Locale' e 'ASIN' che dovrebbero essere i nomi standardizzati dopo il caricamento
        keepa_df_combined.drop_duplicates(subset=['ASIN', 'Locale'], keep='last', inplace=True)
        logger.info(f"Combined and de-duplicated Keepa data from {valid_keepa_files_count} valid file(s): {len(keepa_df_combined)} rows.")
        
        keepa_df_combined['Sito_mapped'] = mapping.map_locale_to_sito_column(keepa_df_combined, 'Locale')
        
        # Rinominazione delle colonne Keepa ai nomi interni usati dall'app
        # Usa i nomi delle colonne come vengono letti dai file (prima della pulizia prezzo)
        keepa_df_combined.rename(columns={
            "Buy Box: Current": "buybox_price",      # Nome da Excel (se usato)
            "Buy Box 🚚: Corrente": "buybox_price", # Nome da CSV (se usato)
            "Categories: Root": "Category",         # Nome da Excel (se usato)
            "Categorie: Radice": "Category"         # Nome da CSV (se usato)
        }, inplace=True, errors='ignore') # errors='ignore' è importante se una colonna non è in tutti i file
                                          # o se un file usa un nome e un altro file usa l'altro
        
        if 'buybox_price' in keepa_df_combined.columns:
            logger.info("Cleaning 'buybox_price' column from Keepa data...")
            keepa_df_combined['buybox_price'] = keepa_df_combined['buybox_price'].astype(str).str.replace('€', '', regex=False).str.replace(r'\s+', '', regex=True).str.replace(',', '.', regex=False)
            keepa_df_combined['buybox_price'] = pd.to_numeric(keepa_df_combined['buybox_price'], errors='coerce')
            logger.info("'buybox_price' column cleaned and converted to numeric.")
        else:
            logger.warning("'buybox_price' (o il suo originale) non trovato nel DataFrame Keepa combinato dopo la rinominazione.")
            keepa_df_combined['buybox_price'] = pd.NA # Aggiungi come colonna vuota se manca del tutto

        if 'Category' not in keepa_df_combined.columns:
            logger.warning("'Category' (o il suo originale) non trovato nel DataFrame Keepa combinato dopo la rinominazione.")
            keepa_df_combined['Category'] = pd.NA # Aggiungi come colonna vuota se manca

        logger.info("Combined Keepa data mapped and columns renamed/cleaned.")
        
        amazon_df['Codice'] = amazon_df['Codice'].astype(str)
        keepa_df_combined['ASIN'] = keepa_df_combined['ASIN'].astype(str)

        merged_df = pd.merge(
            amazon_df,
            keepa_df_combined[['ASIN', 'Sito_mapped', 'buybox_price', 'Category']], 
            left_on=['Codice', 'Sito'],
            right_on=['ASIN', 'Sito_mapped'],
            how='left'
        )
        logger.info(f"Data merged: {len(merged_df)} rows.")

        merged_df['amazon_fee_pct_col'] = float(st.session_state.last_fee_pct)
        merged_df['shipping_cost'] = pricing.calculate_initial_shipping_cost(merged_df, 'Sito')
        merged_df['buybox_price'] = pd.to_numeric(merged_df['buybox_price'], errors='coerce')

        merged_df = pricing.update_all_calculated_columns(merged_df, float(st.session_state.last_fee_pct))
        logger.info("Calculated columns initialized for the main grid.")
        
        st.session_state.processed_df = merged_df.copy()
        st.success("Dati elaborati con successo per la griglia!")
        st.rerun()

    except io_layer.InvalidFileFormatError as e:
        st.error(f"Errore formato file (Elaborazione Principale): {e}")
        logger.error(f"Main Processing - InvalidFileFormatError: {e}")
        st.session_state.processed_df = None
    except Exception as e:
        st.error(f"Errore durante l'elaborazione principale: {e}")
        logger.error(f"Main Processing error: {e}", exc_info=True)
        st.session_state.processed_df = None

if st.session_state.processed_df is not None:
    current_df = st.session_state.processed_df.copy()

    fee_col_present = 'amazon_fee_pct_col' in current_df.columns
    grid_fee_value = current_df['amazon_fee_pct_col'].iloc[0] if fee_col_present and not current_df.empty else float(st.session_state.last_fee_pct)
    
    if float(st.session_state.last_fee_pct) != grid_fee_value :
        current_df['amazon_fee_pct_col'] = float(st.session_state.last_fee_pct)
        current_df = pricing.update_all_calculated_columns(current_df, float(st.session_state.last_fee_pct))
        st.session_state.processed_df = current_df.copy()
        st.rerun()

    gb = GridOptionsBuilder.from_dataframe(current_df)
    gb.configure_default_column(editable=False, resizable=True, sortable=True, filter=True, wrapText=False, autoHeight=False)
    gb.configure_column("nostro_prezzo", editable=True, type=["numericColumn", "numberColumnFilter", "customNumericFormat"], precision=2)
    gb.configure_column("shipping_cost", editable=True, type=["numericColumn", "numberColumnFilter", "customNumericFormat"], precision=2)
    gb.configure_selection(selection_mode="multiple", use_checkbox=True)

    js_row_style = JsCode("""function(params) { if (params.data.net_margin < 0) { return { 'background-color': '#FF7F7F' }; } return null; }""")
    gb.configure_grid_options(getRowStyle=js_row_style)
    
    currency_formatter = JsCode("""function(params) { return (params.value !== null && params.value !== undefined && !isNaN(parseFloat(params.value))) ? parseFloat(params.value).toFixed(2) + ' €' : ''; }""")
    percentage_formatter = JsCode("""function(params) { return (params.value !== null && params.value !== undefined && !isNaN(parseFloat(params.value))) ? parseFloat(params.value).toFixed(2) + ' %' : ''; }""")

    for col_name_grid in ['buybox_price', 'diff_euro', 'nostro_prezzo', 'shipping_cost', 'net_margin']:
        if col_name_grid in current_df.columns:
            gb.configure_column(col_name_grid, valueFormatter=currency_formatter, type=["numericColumn", "numberColumnFilter"])
    if 'diff_pct' in current_df.columns:
        gb.configure_column('diff_pct', valueFormatter=percentage_formatter, type=["numericColumn", "numberColumnFilter"])

    gridOptions = gb.build()
    st.header("📊 Griglia Dati Editabile")
    grid_response = AgGrid(current_df, gridOptions=gridOptions, update_mode=GridUpdateMode.MODEL_CHANGED, fit_columns_on_grid_load=True, allow_unsafe_jscode=True, height=600, width='100%')
    edited_df_from_grid = grid_response['data']
    selected_rows = grid_response['selected_rows']

    if edited_df_from_grid is not None:
        edited_df_from_grid_pd = pd.DataFrame(edited_df_from_grid)
        for col_edit in ['nostro_prezzo', 'shipping_cost']:
            if col_edit in edited_df_from_grid_pd.columns:
                 edited_df_from_grid_pd[col_edit] = pd.to_numeric(edited_df_from_grid_pd[col_edit], errors='coerce')
        cols_to_check_for_changes = ['nostro_prezzo', 'shipping_cost']
        cols_exist_in_original = all(col in st.session_state.processed_df.columns for col in cols_to_check_for_changes)
        cols_exist_in_edited = all(col in edited_df_from_grid_pd.columns for col in cols_to_check_for_changes)
        if cols_exist_in_original and cols_exist_in_edited:
            original_subset = st.session_state.processed_df[cols_to_check_for_changes]
            edited_subset = edited_df_from_grid_pd[cols_to_check_for_changes]
            if not original_subset.equals(edited_subset):
                logger.info("Grid data changed by user edit.")
                recalculated_df = pricing.update_all_calculated_columns(edited_df_from_grid_pd, float(st.session_state.last_fee_pct))
                st.session_state.processed_df = recalculated_df.copy()
                st.rerun()
        elif edited_df_from_grid_pd.shape != st.session_state.processed_df.shape or not cols_exist_in_original or not cols_exist_in_edited :
            logger.info("Grid data shape changed or key columns missing/mismatch for comparison.")
            if not edited_df_from_grid_pd.empty:
                recalculated_df = pricing.update_all_calculated_columns(edited_df_from_grid_pd, float(st.session_state.last_fee_pct))
                st.session_state.processed_df = recalculated_df.copy()
                st.rerun()

    st.header("🛠️ Azioni di Massa")
    if selected_rows:
        st.info(f"{len(selected_rows)} righe selezionate.")
        selected_indices = [row['_selectedRowNodeInfo']['nodeRowIndex'] for row in selected_rows]
    else:
        st.info("Nessuna riga selezionata.")
        selected_indices = []
    col1, col2, col3 = st.columns(3)
    with col1:
        st.subheader("Scala Prezzo")
        scale_value = st.number_input("Valore Scala", value=0.0, step=0.01, format="%.2f", key="scale_val")
        scale_type = st.radio("Tipo Scala", ["€", "%"], key="scale_type_radio")
        if st.button("Applica Scala Prezzo", disabled=not selected_indices):
            df_after_scale = pricing.apply_scale_price(st.session_state.processed_df.copy(), selected_indices, scale_value, (scale_type == "%"))
            st.session_state.processed_df = pricing.update_all_calculated_columns(df_after_scale, float(st.session_state.last_fee_pct))
            logger.info(f"Applied 'Scala Prezzo' to {len(selected_indices)} rows.")
            st.rerun()
    with col2:
        st.subheader("Allinea a Buy Box – Δ")
        delta_value = st.number_input("Valore Delta (Δ)", value=0.0, step=0.01, format="%.2f", key="delta_val")
        delta_type = st.radio("Tipo Delta", ["€", "%"], key="delta_type_radio")
        if st.button("Applica Allineamento Buy Box", disabled=not selected_indices):
            df_after_align = pricing.apply_align_to_buybox(st.session_state.processed_df.copy(), selected_indices, delta_value, (delta_type == "%"))
            st.session_state.processed_df = pricing.update_all_calculated_columns(df_after_align, float(st.session_state.last_fee_pct))
            logger.info(f"Applied 'Allinea a Buy Box' to {len(selected_indices)} rows.")
            st.rerun()
    with col3:
        st.subheader("Esporta")
        if st.button("💾 Esporta Ready Pro CSV"):
            if st.session_state.processed_df is not None and not st.session_state.processed_df.empty:
                try:
                    output_csv_bytes = io_layer.save_ready_pro_csv(st.session_state.processed_df, st.session_state.original_amazon_columns)
                    export_filename = f"updated_{st.session_state.amazon_filename}"
                    st.download_button(label=f"Scarica {export_filename}", data=output_csv_bytes, file_name=export_filename, mime="text/csv")
                    logger.info(f"Exported data to {export_filename}.")
                    st.success(f"File {export_filename} pronto per il download.")
                except Exception as e:
                    st.error(f"Errore esportazione: {e}")
                    logger.error(f"Export error: {e}", exc_info=True)
            else:
                st.warning("Nessun dato da esportare.")
elif not uploaded_amazon_file:
    st.info("📈 Carica il file Inserzioni Amazon.")
elif not uploaded_keepa_files and uploaded_amazon_file:
     st.info("⬆️ File Amazon caricato. Ora carica i file Keepa e clicca 'Elabora Dati Principali'.")