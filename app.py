import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode, ColumnsAutoSizeMode, JsCode
import pandas as pd
import logging
from logging.handlers import TimedRotatingFileHandler
import yaml
from pathlib import Path
from io import BytesIO

from services import io_layer, pricing, mapping

st.set_page_config(page_title="Repricer Ready Pro + Keepa", layout="wide")

LOG_FILE = "repricer.log"
logger = logging.getLogger("RepricerApp")
logger.setLevel(logging.INFO)
if not logger.handlers:
    fh = TimedRotatingFileHandler(LOG_FILE, when="W0", interval=1, backupCount=4, encoding='utf-8')
    fh.setLevel(logging.INFO); formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'); fh.setFormatter(formatter); logger.addHandler(fh)
    ch = logging.StreamHandler(); ch.setLevel(logging.INFO); ch.setFormatter(formatter); logger.addHandler(ch)

def load_app_config() -> dict:
    try:
        with open(Path(__file__).parent / "config/amazon_fees.yml", "r") as f: config = yaml.safe_load(f)
        logger.info("Configuration loaded."); return config
    except Exception as e: st.error(f"Error config: {e}"); logger.error(f"Error config: {e}"); return {"default_fee_pct": 15}
app_config = load_app_config()

if 'processed_df' not in st.session_state: st.session_state.processed_df = None
if 'original_amazon_columns' not in st.session_state: st.session_state.original_amazon_columns = []
if 'original_amazon_dtypes' not in st.session_state: st.session_state.original_amazon_dtypes = {}
if 'amazon_filename' not in st.session_state: st.session_state.amazon_filename = "ready_pro_export.csv"
if 'last_fee_pct' not in st.session_state: st.session_state.last_fee_pct = app_config.get('default_fee_pct', 15)
if 'asins_for_keepa_search' not in st.session_state: st.session_state.asins_for_keepa_search = None
if 'amazon_df_loaded' not in st.session_state: st.session_state.amazon_df_loaded = None
if 'last_uploaded_amazon_file_name' not in st.session_state: st.session_state.last_uploaded_amazon_file_name = None
if 'cost_df_loaded' not in st.session_state: st.session_state.cost_df_loaded = None
if 'amazon_fees_df' not in st.session_state: st.session_state.amazon_fees_df = None
if 'amazon_categories_list' not in st.session_state: st.session_state.amazon_categories_list = [""] 
if 'last_fees_file_name' not in st.session_state: st.session_state.last_fees_file_name = None
if 'last_cost_file_name' not in st.session_state: st.session_state.last_cost_file_name = None

st.title("🏷️ Repricer Ready Pro + Keepa")
with st.expander("ℹ️ Istruzioni per l'Uso", expanded=True):
    st.markdown("""
    Benvenuto! Quest'app ottimizza i prezzi dei tuoi prodotti Amazon.
    **Nuova Funzionalità: Commissioni Amazon per Categoria!**

    **Passaggi:**
    1.  **Carica File Commissioni Amazon (Consigliato):** Sidebar -> "0. ...". Deve contenere `Category` e colonne per marketplace (es. `Amazon.it`). Se omesso, usa commissione globale.
    2.  **Carica File Inserzioni Amazon:** Sidebar -> "1. ...". Export Ready Pro (`SKU`, `Codice(ASIN)`, `Sito`, `Prz.aggiornato`). Estrae ASIN per Keepa.
    3.  **Carica File Costi Prodotto (Opzionale):** Sidebar -> "2. ...". Colonne: `"Codice"` (SKU), `"Prezzo medio"` (costo). Separatore `;`, decimale `,`. Se omesso, costo_acquisto = 0.
    4.  **Carica File Keepa:** Sidebar -> "3. ...". CSV o XLSX.
        *   CSV: `"Locale"`, `"ASIN"`, `"Buy Box 🚚: Corrente"`, `"Gruppo di visualizzazione del sito web: Nome"` (categoria).
        *   XLSX: `Locale`, `ASIN`, `Buy Box: Current`, `Categories: Root`.
    5.  **Imposta Comm. Globale (Fallback):** Slider per default se commissione per categoria non applicabile.
    6.  **Elabora Dati:** Click "🔄 Elabora Dati Principali".

    **Griglia:**
    *   **`amazon_category_selected` (Editabile):** Seleziona la categoria Amazon. Determina la commissione.
    *   **`amazon_fee_pct_col`**: Comm. % calcolata per riga. *Per commissioni scalari (es. "15% fino a X; 10% oltre X"), usa la **prima** %.*
    *   Altre colonne: `nostro_prezzo` (edit.), `shipping_cost` (edit.), `costo_acquisto` (edit. se file caricato), `buybox_price`, `diff_euro`, `diff_pct`, `net_margin`.
    *   `net_margin < 0` in rosso. Aggiornamenti live.

    **Azioni di Massa:** Su righe selezionate: "Scala Prezzo" (€ o %), "Allinea a Buy Box – Δ".
    **Esporta:** "💾 Esporta Ready Pro CSV" (UTF-8-BOM, `;`, `,`).
    """)
st.markdown("---")

with st.sidebar:
    st.header("📂 Caricamento File")
    uploaded_fees_file = st.file_uploader("0. Carica File Commissioni Amazon.CSV", type=["csv"], key="fees_file_uploader")
    uploaded_amazon_file = st.file_uploader("1. Carica Inserzioni Amazon.CSV", type=["csv"], key="amazon_file_uploader")
    asin_extraction_placeholder = st.empty()
    uploaded_cost_file = st.file_uploader("2. Carica File Costi Prodotto.CSV (Opzionale)", type=["csv"], key="cost_file_uploader")
    uploaded_keepa_files = st.file_uploader("3. Carica File Keepa (CSV o XLSX)", type=["csv", "xlsx"], accept_multiple_files=True, key="keepa_files_uploader")
    st.header("⚙️ Impostazioni Globali")
    amazon_fee_pct_slider = st.slider("Comm. Amazon Globale (%) (Fallback)", 0, 100, value=st.session_state.last_fee_pct, key="amazon_fee_pct_slider_key")
    st.session_state.last_fee_pct = amazon_fee_pct_slider
    process_button = st.button("🔄 Elabora Dati Principali", disabled=not (uploaded_amazon_file and uploaded_keepa_files))

if uploaded_fees_file:
    if st.session_state.last_fees_file_name != uploaded_fees_file.name or st.session_state.amazon_fees_df is None:
        try:
            logger.info(f"Loading Amazon Fees file: {uploaded_fees_file.name}")
            fees_file_bytes_copy = BytesIO(uploaded_fees_file.getvalue())
            st.session_state.amazon_fees_df = io_layer.load_amazon_fees_csv(fees_file_bytes_copy)
            st.session_state.amazon_categories_list = [""] + sorted(st.session_state.amazon_fees_df.index.tolist())
            st.session_state.last_fees_file_name = uploaded_fees_file.name
            logger.info(f"Amazon Fees file loaded: {len(st.session_state.amazon_fees_df)} categories.")
            st.sidebar.success(f"File commissioni '{uploaded_fees_file.name}' caricato.")
        except Exception as e_fees: st.sidebar.error(f"Errore File Commissioni: {e_fees}"); logger.error(f"Error Fees file: {e_fees}", exc_info=True); st.session_state.amazon_fees_df = None; st.session_state.amazon_categories_list = [""]; st.session_state.last_fees_file_name = None
elif 'amazon_fees_df' in st.session_state and st.session_state.amazon_fees_df is not None and uploaded_fees_file is None:
    logger.info("Fees file uploader empty."); st.session_state.amazon_fees_df = None; st.session_state.amazon_categories_list = [""]; st.session_state.last_fees_file_name = None; st.sidebar.info("File commissioni rimosso.")

if uploaded_amazon_file:
    if st.session_state.last_uploaded_amazon_file_name != uploaded_amazon_file.name or st.session_state.asins_for_keepa_search is None:
        try:
            amazon_file_bytes_copy = BytesIO(uploaded_amazon_file.getvalue())
            temp_amazon_df, cols, dtypes = io_layer.load_amazon_csv(amazon_file_bytes_copy)
            st.session_state.amazon_df_loaded = temp_amazon_df.copy(); st.session_state.amazon_filename = uploaded_amazon_file.name
            st.session_state.original_amazon_columns = cols; st.session_state.original_amazon_dtypes = dtypes
            st.session_state.asins_for_keepa_search = io_layer.extract_asins_for_keepa_search(temp_amazon_df)
            st.session_state.last_uploaded_amazon_file_name = uploaded_amazon_file.name; logger.info("ASINs extracted.")
        except Exception as e: asin_extraction_placeholder.error(f"Errore estrazione ASIN: {e}"); logger.error(f"ASIN Extraction error: {e}", exc_info=True); st.session_state.asins_for_keepa_search = None; st.session_state.amazon_df_loaded = None; st.session_state.last_uploaded_amazon_file_name = None
    if st.session_state.asins_for_keepa_search:
        with asin_extraction_placeholder.container():
            st.subheader("📋 ASIN per Ricerca Keepa"); st.caption("Copia e incolla su Keepa.")
            for loc, asins_str in sorted(st.session_state.asins_for_keepa_search.items()):
                if asins_str.count('\n') + (1 if asins_str else 0) > 0:
                    with st.expander(f"{loc.upper()} ({mapping.LOCALE_TO_SITO_MAP.get(loc, loc)}) - {asins_str.count(chr(10)) + (1 if asins_str else 0)} ASIN"): st.code(asins_str, language=None)
            st.markdown("---")
    elif st.session_state.amazon_df_loaded is not None and not st.session_state.asins_for_keepa_search:
         with asin_extraction_placeholder.container(): st.warning("File Amazon caricato, ma nessun ASIN estratto/mappato."); st.markdown("---")

if uploaded_cost_file:
    if st.session_state.last_cost_file_name != uploaded_cost_file.name or st.session_state.cost_df_loaded is None:
        try:
            cost_file_bytes_copy = BytesIO(uploaded_cost_file.getvalue())
            st.session_state.cost_df_loaded = io_layer.load_cost_csv(cost_file_bytes_copy)
            st.session_state.last_cost_file_name = uploaded_cost_file.name
            logger.info(f"Cost file loaded: {len(st.session_state.cost_df_loaded)} SKUs.")
            st.sidebar.success(f"File costi '{uploaded_cost_file.name}' caricato ({len(st.session_state.cost_df_loaded)} righe).")
        except Exception as e_cost: st.sidebar.error(f"Errore File Costi: {e_cost}"); logger.error(f"Error Cost file: {e_cost}", exc_info=True); st.session_state.cost_df_loaded = None; st.session_state.last_cost_file_name = None
elif 'cost_df_loaded' in st.session_state and st.session_state.cost_df_loaded is not None and uploaded_cost_file is None:
    logger.info("Cost file uploader empty."); st.session_state.cost_df_loaded = None; st.session_state.last_cost_file_name = None; st.sidebar.info("File costi rimosso.")

if process_button and uploaded_amazon_file and uploaded_keepa_files:
    try:
        logger.info("Starting main data processing.")
        if st.session_state.amazon_df_loaded is not None and st.session_state.amazon_filename == uploaded_amazon_file.name:
            amazon_df = st.session_state.amazon_df_loaded.copy()
        else:
            amazon_file_bytes_main = BytesIO(uploaded_amazon_file.getvalue())
            amazon_df, st.session_state.original_amazon_columns, st.session_state.original_amazon_dtypes = io_layer.load_amazon_csv(amazon_file_bytes_main)
            st.session_state.amazon_filename = uploaded_amazon_file.name
        logger.info(f"Amazon CSV for grid: {len(amazon_df)} rows.")
        all_keepa_dfs = []
        for k_file in uploaded_keepa_files:
            try:
                if k_file.name.lower().endswith(".csv"): df_k = io_layer.load_keepa_csv(k_file)
                elif k_file.name.lower().endswith(".xlsx"): df_k = io_layer.load_keepa_xlsx(k_file)
                else: st.warning(f"Formato Keepa non supp.: '{k_file.name}'."); continue
                all_keepa_dfs.append(df_k)
            except Exception as e_k: st.warning(f"File Keepa '{k_file.name}' ignorato: {e_k}"); logger.warning(f"Skipping Keepa '{k_file.name}': {e_k}")
        if not all_keepa_dfs: st.error("Nessun file Keepa valido."); logger.error("No valid Keepa files."); st.session_state.processed_df = None; st.stop()
        
        keepa_df = pd.concat(all_keepa_dfs, ignore_index=True)
        keepa_df.drop_duplicates(subset=['ASIN', 'Locale'], keep='last', inplace=True)
        keepa_df['Sito_mapped'] = mapping.map_locale_to_sito_column(keepa_df, 'Locale')
        keepa_df.rename(columns={"Buy Box: Current": "buybox_price", "Buy Box 🚚: Corrente": "buybox_price", "Categories: Root": "Category_Keepa", "Gruppo di visualizzazione del sito web: Nome": "Category_Keepa"}, inplace=True, errors='ignore')
        if 'buybox_price' in keepa_df.columns:
            keepa_df['buybox_price'] = keepa_df['buybox_price'].astype(str).str.replace('€', '', regex=False).str.replace(r'\s+', '', regex=True).str.replace(',', '.', regex=False)
            keepa_df['buybox_price'] = pd.to_numeric(keepa_df['buybox_price'], errors='coerce')
        else: keepa_df['buybox_price'] = pd.NA
        if 'Category_Keepa' not in keepa_df.columns: keepa_df['Category_Keepa'] = pd.NA
        
        merged_df = pd.merge(amazon_df, keepa_df[['ASIN', 'Sito_mapped', 'buybox_price', 'Category_Keepa']], left_on=['Codice', 'Sito'], right_on=['ASIN', 'Sito_mapped'], how='left')
        
        if st.session_state.cost_df_loaded is not None and not st.session_state.cost_df_loaded.empty:
            if 'SKU' in merged_df.columns:
                merged_df['SKU'] = merged_df['SKU'].astype(str)
                merged_df = pd.merge(merged_df, st.session_state.cost_df_loaded[['SKU_cost', 'costo_acquisto']], left_on='SKU', right_on='SKU_cost', how='left')
                merged_df.drop(columns=['SKU_cost'], inplace=True, errors='ignore'); merged_df['costo_acquisto'].fillna(0, inplace=True)
            else: merged_df['costo_acquisto'] = 0.0
        else: merged_df['costo_acquisto'] = 0.0
        
        if 'amazon_category_selected' not in merged_df.columns:
            if 'Category_Keepa' in merged_df.columns and st.session_state.amazon_fees_df is not None:
                def find_match(keepa_cat_val):
                    if pd.isna(keepa_cat_val): return ""
                    for amz_cat_val in st.session_state.amazon_categories_list:
                        if amz_cat_val and isinstance(keepa_cat_val, str) and keepa_cat_val.lower() in amz_cat_val.lower(): return amz_cat_val
                    return ""
                merged_df['amazon_category_selected'] = merged_df['Category_Keepa'].apply(find_match)
            else: merged_df['amazon_category_selected'] = ""
        
        merged_df['shipping_cost'] = pricing.calculate_initial_shipping_cost(merged_df, 'Sito')
        for col in ['buybox_price', 'nostro_prezzo', 'costo_acquisto']: merged_df[col] = pd.to_numeric(merged_df[col], errors='coerce')
        merged_df['costo_acquisto'].fillna(0, inplace=True)
        
        st.session_state.processed_df = pricing.update_all_calculated_columns(merged_df, st.session_state.amazon_fees_df, st.session_state.last_fee_pct).copy()
        st.success("Dati elaborati!"); st.rerun()
    except Exception as e: st.error(f"Errore elaborazione: {e}"); logger.error(f"Processing error: {e}", exc_info=True); st.session_state.processed_df = None

if st.session_state.processed_df is not None:
    current_df = st.session_state.processed_df.copy()
    gb = GridOptionsBuilder.from_dataframe(current_df)
    gb.configure_default_column(editable=False, resizable=True, sortable=True, filter=True, wrapText=False, autoHeight=False)
    editable_cols = {"nostro_prezzo": 2, "shipping_cost": 2}
    if 'costo_acquisto' in current_df.columns: editable_cols["costo_acquisto"] = 2
    for col, prec in editable_cols.items(): gb.configure_column(col, editable=True, type=["numericColumn"], precision=prec)
    if 'amazon_category_selected' in current_df.columns:
        gb.configure_column("amazon_category_selected", header_name="Categoria Amazon", editable=True, cellEditor='agSelectCellEditor', cellEditorParams={'values': st.session_state.amazon_categories_list}, width=250)
    gb.configure_selection(selection_mode="multiple", use_checkbox=True)
    js_row_style = JsCode("""function(params) { if (params.data.net_margin < 0) { return { 'background-color': '#FF7F7F' }; } return null; }""")
    gb.configure_grid_options(getRowStyle=js_row_style)
    currency_fmt = JsCode("""function(params) { return (params.value !== null && !isNaN(parseFloat(params.value))) ? parseFloat(params.value).toFixed(2) + ' €' : ''; }""")
    percent_fmt = JsCode("""function(params) { return (params.value !== null && !isNaN(parseFloat(params.value))) ? parseFloat(params.value).toFixed(2) + ' %' : ''; }""")
    for col in ['buybox_price', 'diff_euro', 'nostro_prezzo', 'shipping_cost', 'net_margin', 'costo_acquisto']:
        if col in current_df.columns: gb.configure_column(col, valueFormatter=currency_fmt, type=["numericColumn"])
    for col in ['diff_pct', 'amazon_fee_pct_col']:
        if col in current_df.columns: gb.configure_column(col, header_name=f"Comm. Amazon (%)" if col == 'amazon_fee_pct_col' else col, valueFormatter=percent_fmt, type=["numericColumn"])
    gridOptions = gb.build()
    st.header("📊 Griglia Dati Editabile")
    grid_response = AgGrid(current_df, gridOptions=gridOptions, data_return_mode=DataReturnMode.AS_INPUT, update_mode=GridUpdateMode.MODEL_CHANGED, fit_columns_on_grid_load=False, allow_unsafe_jscode=True, height=600, width='100%', columns_auto_size_mode=ColumnsAutoSizeMode.FIT_CONTENTS)
    edited_df = pd.DataFrame(grid_response['data']) if grid_response['data'] is not None else None
    
    if edited_df is not None and not st.session_state.processed_df.equals(edited_df):
        logger.info("Grid data changed.")
        st.session_state.processed_df = pricing.update_all_calculated_columns(edited_df, st.session_state.amazon_fees_df, st.session_state.last_fee_pct).copy()
        st.rerun()

    selected_rows = grid_response['selected_rows']
    st.header("🛠️ Azioni di Massa")
    # ... (Azioni di massa e Esportazione come nella versione precedente, assicurandosi che le chiamate a update_all_calculated_columns includano st.session_state.amazon_fees_df)
    selected_indices = [row['_selectedRowNodeInfo']['nodeRowIndex'] for row in selected_rows] if selected_rows else []
    if not selected_rows: st.info("Nessuna riga selezionata.")
    else: st.info(f"{len(selected_rows)} righe selezionate.")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.subheader("Scala Prezzo")
        scale_val = st.number_input("Valore Scala", value=0.0, step=0.01, format="%.2f", key="s_val")
        scale_t = st.radio("Tipo Scala", ["€", "%"], key="s_type")
        if st.button("Applica Scala", disabled=not selected_indices):
            df_mod = pricing.apply_scale_price(st.session_state.processed_df.copy(),selected_indices,scale_val,(scale_t=="%"))
            st.session_state.processed_df = pricing.update_all_calculated_columns(df_mod, st.session_state.amazon_fees_df, st.session_state.last_fee_pct)
            logger.info("Applied Scala Prezzo."); st.rerun()
    with col2:
        st.subheader("Allinea a Buy Box – Δ")
        delta_val = st.number_input("Valore Delta (Δ)", value=0.0,step=0.01,format="%.2f",key="d_val")
        delta_t = st.radio("Tipo Delta",["€","%"],key="d_type")
        if st.button("Applica Allinea",disabled=not selected_indices):
            df_mod = pricing.apply_align_to_buybox(st.session_state.processed_df.copy(),selected_indices,delta_val,(delta_t=="%"))
            st.session_state.processed_df = pricing.update_all_calculated_columns(df_mod, st.session_state.amazon_fees_df, st.session_state.last_fee_pct)
            logger.info("Applied Allinea Buy Box."); st.rerun()
    with col3:
        st.subheader("Esporta")
        if st.button("💾 Esporta Ready Pro CSV"):
            if st.session_state.processed_df is not None and not st.session_state.processed_df.empty:
                try:
                    csv_bytes = io_layer.save_ready_pro_csv(st.session_state.processed_df, st.session_state.original_amazon_columns)
                    st.download_button(f"Scarica updated_{st.session_state.amazon_filename}", csv_bytes, f"updated_{st.session_state.amazon_filename}", "text/csv")
                    logger.info("Exported data."); st.success("File esportato.")
                except Exception as e: st.error(f"Errore esportazione: {e}"); logger.error(f"Export error: {e}", exc_info=True)
            else: st.warning("Nessun dato da esportare.")

elif not uploaded_amazon_file: st.info("📈 Carica file Inserzioni Amazon.")
elif not uploaded_keepa_files: st.info("⬆️ Carica file Keepa (e opz. Costi/Commissioni).")