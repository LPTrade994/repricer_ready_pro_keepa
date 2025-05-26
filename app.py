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
if 'processed_df' not in st.session_state: st.session_state.processed_df = None
if 'original_amazon_columns' not in st.session_state: st.session_state.original_amazon_columns = []
if 'original_amazon_dtypes' not in st.session_state: st.session_state.original_amazon_dtypes = {}
if 'amazon_filename' not in st.session_state: st.session_state.amazon_filename = "ready_pro_export.csv"
if 'last_fee_pct' not in st.session_state: st.session_state.last_fee_pct = app_config.get('default_fee_pct', 15)
if 'asins_for_keepa_search' not in st.session_state: st.session_state.asins_for_keepa_search = None
if 'amazon_df_loaded' not in st.session_state: st.session_state.amazon_df_loaded = None
if 'last_uploaded_amazon_file_name' not in st.session_state: st.session_state.last_uploaded_amazon_file_name = None
if 'cost_df_loaded' not in st.session_state: st.session_state.cost_df_loaded = None


# --- INSTRUCTIONS SECTION ---
st.title("🏷️ Repricer Ready Pro + Keepa")

with st.expander("ℹ️ Istruzioni per l'Uso", expanded=True):
    st.markdown("""
    Benvenuto nell'app Repricer Ready Pro + Keepa! Questa applicazione ti aiuta a ottimizzare i prezzi dei tuoi prodotti Amazon.

    **Passaggi da Seguire:**

    1.  **Carica il File Inserzioni Amazon:**
        *   Utilizza il box "1. Carica Inserzioni Amazon.CSV" nella sidebar.
        *   Questo file deve essere l'export standard delle tue inserzioni da Ready Pro. Colonne attese:
            *   `SKU`
            *   `Codice(ASIN)` (verrà usato come ASIN)
            *   `Sito` (es. `Italia - Amazon.it`)
            *   `Prz.aggiornato` (il tuo prezzo di vendita attuale)
        *   Una volta caricato, l'app estrarrà automaticamente gli ASIN per ogni paese. Potrai copiarli per cercarli su Keepa.

    2.  **Carica il File Costi Prodotto (Opzionale ma Consigliato):**
        *   Utilizza il box "2. Carica File Costi Prodotto.CSV" nella sidebar.
        *   Questo file deve contenere i tuoi costi d'acquisto. Formato atteso:
            *   Colonna 1: `"Codice"` (che deve corrispondere allo `SKU` del file Inserzioni Amazon).
            *   Colonna 2: `"Prezzo medio"` (il tuo costo d'acquisto, es. `10,50`).
            *   Il file deve usare il **punto e virgola (`;`)** come separatore e la **virgola (`,`)** per i decimali.
        *   Se non carichi questo file, il `costo_acquisto` sarà considerato 0 nel calcolo del margine netto.

    3.  **Carica i File Keepa:**
        *   Utilizza il box "3. Carica File Keepa" nella sidebar.
        *   Puoi caricare uno o più file esportati da Keepa (preferibilmente in formato `.csv`).
        *   I file CSV Keepa devono contenere almeno le colonne (i nomi devono essere esatti, virgolette incluse se presenti nel file):
            *   `"Locale"` (es. it, fr)
            *   `"ASIN"`
            *   `"Buy Box 🚚: Corrente"` (per il prezzo della Buy Box)
            *   `"Gruppo di visualizzazione del sito web: Nome"` (per la categoria)
        *   Se carichi file `.xlsx` da Keepa, le colonne attese sono: `Locale`, `ASIN`, `Buy Box: Current`, `Categories: Root`.
        *   Se carichi più file Keepa, verranno combinati. In caso di duplicati ASIN/Locale, verrà mantenuto l'ultimo caricato.

    4.  **Imposta la Commissione Amazon:**
        *   Usa lo slider "Commissione Amazon (%)" per impostare la percentuale di commissione media.

    5.  **Elabora i Dati:**
        *   Clicca sul bottone "🔄 Elabora Dati Principali".
        *   L'app unirà tutti i dati e calcolerà le colonne aggiuntive.

    **Funzionalità della Griglia:**

    *   **Colonne Editabili**: `nostro_prezzo`, `shipping_cost`, e `costo_acquisto` (se il file costi è caricato).
    *   **Colonne Calcolate**:
        *   `buybox_price`: Prezzo Buy Box da Keepa.
        *   `costo_acquisto`: Tuo costo d'acquisto.
        *   `diff_euro`, `diff_pct`: Differenze rispetto alla Buy Box.
        *   `amazon_fee_pct_col`: Commissione Amazon (%).
        *   `shipping_cost`: Costo spedizione (default 5,14€ per Italia, 11,50€ altrimenti; editabile).
        *   `net_margin`: `nostro_prezzo - (commissione) - shipping_cost - costo_acquisto`.
    *   **Evidenziazione Righe**: Righe con `net_margin < 0` in rosso.
    *   **Aggiornamenti Live**: Le colonne calcolate si aggiornano dopo le modifiche.

    **Azioni di Massa (su righe selezionate):**

    *   **Scala Prezzo**: Sconto fisso (€) o percentuale (%).
    *   **Allinea a Buy Box – Δ**: Prezzo = `buybox_price - Δ`.

    **Esportazione:**

    *   Clicca "💾 Esporta Ready Pro CSV" per scaricare un file CSV con i prezzi aggiornati, pronto per Ready Pro (UTF-8-BOM, separatore `;`, decimali `,`).
    """)
st.markdown("---")

with st.sidebar:
    st.header("📂 Caricamento File")
    uploaded_amazon_file = st.file_uploader("1. Carica Inserzioni Amazon.CSV", type=["csv"], key="amazon_file_uploader")
    asin_extraction_placeholder = st.empty()
    uploaded_cost_file = st.file_uploader("2. Carica File Costi Prodotto.CSV (Opzionale)", type=["csv"], key="cost_file_uploader")
    uploaded_keepa_files = st.file_uploader("3. Carica File Keepa (CSV o XLSX)", type=["csv", "xlsx"], accept_multiple_files=True, key="keepa_files_uploader")
    st.header("⚙️ Impostazioni Globali")
    amazon_fee_pct_slider = st.slider("Commissione Amazon (%)", 0, 100, value=st.session_state.last_fee_pct, key="amazon_fee_pct_slider_key")
    st.session_state.last_fee_pct = amazon_fee_pct_slider
    process_button = st.button("🔄 Elabora Dati Principali", disabled=not (uploaded_amazon_file and uploaded_keepa_files))

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
            st.session_state.asins_for_keepa_search = None; st.session_state.amazon_df_loaded = None; st.session_state.last_uploaded_amazon_file_name = None
        except Exception as e:
            asin_extraction_placeholder.error(f"Errore estrazione ASIN: {e}")
            logger.error(f"ASIN Extraction - Processing error: {e}", exc_info=True)
            st.session_state.asins_for_keepa_search = None; st.session_state.amazon_df_loaded = None; st.session_state.last_uploaded_amazon_file_name = None
    if st.session_state.asins_for_keepa_search:
        with asin_extraction_placeholder.container():
            st.subheader("📋 ASIN per Ricerca Keepa")
            st.caption("Copia gli ASIN per ogni paese e incollali nella ricerca Bulk ASIN di Keepa.")
            if not st.session_state.asins_for_keepa_search: st.info("Nessun ASIN trovato o mappato.")
            for locale_code, asins_str in sorted(st.session_state.asins_for_keepa_search.items()):
                num_asins = asins_str.count('\n') + 1 if asins_str else 0
                if num_asins > 0:
                    with st.expander(f"{locale_code.upper()} ({mapping.LOCALE_TO_SITO_MAP.get(locale_code, locale_code)}) - {num_asins} ASIN"):
                        st.code(asins_str, language=None)
            st.markdown("---")
    elif st.session_state.amazon_df_loaded is not None and not st.session_state.asins_for_keepa_search:
         with asin_extraction_placeholder.container():
            st.warning("File Amazon caricato, ma nessun ASIN è stato estratto/mappato per Keepa."); st.markdown("---")

if uploaded_cost_file:
    if st.session_state.get('last_cost_file_name') != uploaded_cost_file.name or st.session_state.cost_df_loaded is None:
        try:
            logger.info(f"Loading Cost file: {uploaded_cost_file.name}")
            cost_file_bytes_copy = BytesIO(uploaded_cost_file.getvalue())
            st.session_state.cost_df_loaded = io_layer.load_cost_csv(cost_file_bytes_copy)
            st.session_state.last_cost_file_name = uploaded_cost_file.name
            logger.info(f"Cost file loaded: {len(st.session_state.cost_df_loaded)} SKUs with costs.")
            st.sidebar.success(f"File costi '{uploaded_cost_file.name}' caricato ({len(st.session_state.cost_df_loaded)} righe).")
        except io_layer.InvalidFileFormatError as e_cost:
            st.sidebar.error(f"Errore formato file Costi: {e_cost}")
            logger.error(f"InvalidFileFormatError in Cost file: {e_cost}")
            st.session_state.cost_df_loaded = None
            st.session_state.last_cost_file_name = None
        except Exception as e_general_cost:
            st.sidebar.error(f"Errore caricamento file Costi: {e_general_cost}")
            logger.error(f"Generic error loading Cost file: {e_general_cost}", exc_info=True)
            st.session_state.cost_df_loaded = None
            st.session_state.last_cost_file_name = None
elif 'cost_df_loaded' in st.session_state and st.session_state.cost_df_loaded is not None and uploaded_cost_file is None:
    logger.info("Cost file uploader is empty, resetting loaded cost data.")
    st.session_state.cost_df_loaded = None
    st.session_state.last_cost_file_name = None
    st.sidebar.info("File costi rimosso o non caricato.")


if process_button and uploaded_amazon_file and uploaded_keepa_files:
    try:
        logger.info("Starting main data processing.")
        if st.session_state.amazon_df_loaded is not None and st.session_state.amazon_filename == uploaded_amazon_file.name:
            amazon_df = st.session_state.amazon_df_loaded.copy()
            original_cols = st.session_state.original_amazon_columns
            original_dtypes = st.session_state.original_amazon_dtypes
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
                if keepa_file_single.name.lower().endswith(".csv"): df_single_keepa = io_layer.load_keepa_csv(keepa_file_single)
                elif keepa_file_single.name.lower().endswith(".xlsx"): df_single_keepa = io_layer.load_keepa_xlsx(keepa_file_single)
                else: st.warning(f"Formato Keepa non supportato: '{keepa_file_single.name}'."); logger.warning(f"Unsupported Keepa: '{keepa_file_single.name}'."); continue
                all_keepa_dataframes.append(df_single_keepa); valid_keepa_files_count += 1
            except io_layer.InvalidFileFormatError as e_k: st.warning(f"File Keepa '{keepa_file_single.name}' ignorato: {e_k}"); logger.warning(f"Skipping Keepa '{keepa_file_single.name}': {e_k}")
            except Exception as e_gk: st.error(f"Errore Keepa '{keepa_file_single.name}': {e_gk}"); logger.error(f"Error Keepa '{keepa_file_single.name}': {e_gk}", exc_info=True)
        if not all_keepa_dataframes:
            st.error("Nessun file Keepa valido caricato."); logger.error("No valid Keepa files."); st.session_state.processed_df = None; st.stop()

        keepa_df_combined = pd.concat(all_keepa_dataframes, ignore_index=True)
        keepa_df_combined.drop_duplicates(subset=['ASIN', 'Locale'], keep='last', inplace=True)
        logger.info(f"Combined Keepa data: {len(keepa_df_combined)} rows.")
        keepa_df_combined['Sito_mapped'] = mapping.map_locale_to_sito_column(keepa_df_combined, 'Locale')
        keepa_df_combined.rename(columns={
            "Buy Box: Current": "buybox_price", "Buy Box 🚚: Corrente": "buybox_price",
            "Categories: Root": "Category", "Categorie: Radice": "Category",
            "Gruppo di visualizzazione del sito web: Nome": "Category"
        }, inplace=True, errors='ignore')
        if 'buybox_price' in keepa_df_combined.columns:
            keepa_df_combined['buybox_price'] = keepa_df_combined['buybox_price'].astype(str).str.replace('€', '', regex=False).str.replace(r'\s+', '', regex=True).str.replace(',', '.', regex=False)
            keepa_df_combined['buybox_price'] = pd.to_numeric(keepa_df_combined['buybox_price'], errors='coerce')
        else: keepa_df_combined['buybox_price'] = pd.NA
        if 'Category' not in keepa_df_combined.columns: keepa_df_combined['Category'] = pd.NA
        logger.info("Keepa data mapped/renamed/cleaned.")
        
        amazon_df['Codice'] = amazon_df['Codice'].astype(str)
        if 'ASIN' in keepa_df_combined.columns: keepa_df_combined['ASIN'] = keepa_df_combined['ASIN'].astype(str)
        else: raise KeyError("Colonna 'ASIN' mancante in Keepa DF.")

        merged_df = pd.merge(amazon_df, keepa_df_combined[['ASIN', 'Sito_mapped', 'buybox_price', 'Category']], 
                             left_on=['Codice', 'Sito'], right_on=['ASIN', 'Sito_mapped'], how='left')
        logger.info(f"Merged with Keepa: {len(merged_df)} rows.")

        if st.session_state.cost_df_loaded is not None and not st.session_state.cost_df_loaded.empty:
            if 'SKU' not in merged_df.columns:
                st.warning("Colonna 'SKU' non trovata in Amazon DF per merge costi."); logger.warning("SKU column missing for cost merge.")
                merged_df['costo_acquisto'] = 0.0
            else:
                merged_df['SKU'] = merged_df['SKU'].astype(str)
                merged_df = pd.merge(merged_df, st.session_state.cost_df_loaded[['SKU_cost', 'costo_acquisto']],
                                     left_on='SKU', right_on='SKU_cost', how='left')
                merged_df.drop(columns=['SKU_cost'], inplace=True, errors='ignore')
                merged_df['costo_acquisto'].fillna(0, inplace=True)
                logger.info(f"Merged with Cost data.")
        else:
            merged_df['costo_acquisto'] = 0.0
            logger.info("No Cost data, 'costo_acquisto' defaulted to 0.")

        merged_df['amazon_fee_pct_col'] = float(st.session_state.last_fee_pct)
        merged_df['shipping_cost'] = pricing.calculate_initial_shipping_cost(merged_df, 'Sito')
        merged_df['buybox_price'] = pd.to_numeric(merged_df['buybox_price'], errors='coerce')
        merged_df['nostro_prezzo'] = pd.to_numeric(merged_df['nostro_prezzo'], errors='coerce')
        merged_df['costo_acquisto'] = pd.to_numeric(merged_df['costo_acquisto'], errors='coerce').fillna(0)
        merged_df = pricing.update_all_calculated_columns(merged_df, float(st.session_state.last_fee_pct))
        logger.info("Calculated columns finalized.")
        st.session_state.processed_df = merged_df.copy()
        st.success("Dati elaborati con successo per la griglia!")
        st.rerun()
    except io_layer.InvalidFileFormatError as e:
        st.error(f"Errore formato file: {e}"); logger.error(f"InvalidFileFormatError: {e}"); st.session_state.processed_df = None
    except Exception as e:
        st.error(f"Errore elaborazione: {e}"); logger.error(f"Processing error: {e}", exc_info=True); st.session_state.processed_df = None

if st.session_state.processed_df is not None:
    current_df_display = st.session_state.processed_df.copy()
    fee_col_present = 'amazon_fee_pct_col' in current_df_display.columns
    grid_fee_value = current_df_display['amazon_fee_pct_col'].iloc[0] if fee_col_present and not current_df_display.empty else float(st.session_state.last_fee_pct)
    if float(st.session_state.last_fee_pct) != grid_fee_value :
        current_df_display['amazon_fee_pct_col'] = float(st.session_state.last_fee_pct)
        current_df_display = pricing.update_all_calculated_columns(current_df_display, float(st.session_state.last_fee_pct))
        st.session_state.processed_df = current_df_display.copy()
        st.rerun()

    gb = GridOptionsBuilder.from_dataframe(current_df_display)
    gb.configure_default_column(editable=False, resizable=True, sortable=True, filter=True, wrapText=False, autoHeight=False)
    gb.configure_column("nostro_prezzo", editable=True, type=["numericColumn", "numberColumnFilter", "customNumericFormat"], precision=2)
    gb.configure_column("shipping_cost", editable=True, type=["numericColumn", "numberColumnFilter", "customNumericFormat"], precision=2)
    if 'costo_acquisto' in current_df_display.columns:
        gb.configure_column("costo_acquisto", editable=True, type=["numericColumn", "numberColumnFilter", "customNumericFormat"], precision=2)
    gb.configure_selection(selection_mode="multiple", use_checkbox=True)
    js_row_style = JsCode("""function(params) { if (params.data.net_margin < 0) { return { 'background-color': '#FF7F7F' }; } return null; }""")
    gb.configure_grid_options(getRowStyle=js_row_style)
    currency_formatter = JsCode("""function(params) { return (params.value !== null && params.value !== undefined && !isNaN(parseFloat(params.value))) ? parseFloat(params.value).toFixed(2) + ' €' : ''; }""")
    percentage_formatter = JsCode("""function(params) { return (params.value !== null && params.value !== undefined && !isNaN(parseFloat(params.value))) ? parseFloat(params.value).toFixed(2) + ' %' : ''; }""")
    cols_for_currency_format = ['buybox_price', 'diff_euro', 'nostro_prezzo', 'shipping_cost', 'net_margin']
    if 'costo_acquisto' in current_df_display.columns: cols_for_currency_format.append('costo_acquisto')
    for col_name_grid in cols_for_currency_format:
        if col_name_grid in current_df_display.columns:
            gb.configure_column(col_name_grid, valueFormatter=currency_formatter, type=["numericColumn", "numberColumnFilter"])
    if 'diff_pct' in current_df_display.columns: gb.configure_column('diff_pct', valueFormatter=percentage_formatter, type=["numericColumn", "numberColumnFilter"])
    gridOptions = gb.build()
    st.header("📊 Griglia Dati Editabile")
    grid_response = AgGrid(current_df_display, gridOptions=gridOptions, update_mode=GridUpdateMode.MODEL_CHANGED, fit_columns_on_grid_load=True, allow_unsafe_jscode=True, height=600, width='100%')
    edited_df_from_grid = grid_response['data']
    selected_rows = grid_response['selected_rows']
    if edited_df_from_grid is not None:
        edited_df_from_grid_pd = pd.DataFrame(edited_df_from_grid)
        if not edited_df_from_grid_pd.empty:
            original_df_for_update = st.session_state.processed_df.copy()
            
            # Allinea gli indici per l'aggiornamento corretto
            # Questo assume che l'ordine delle righe non cambi radicalmente e che edited_df_from_grid_pd sia un subset/versione di original_df_for_update
            # Se la griglia permette riordinamenti o filtraggi che cambiano l'indice rispetto al DataFrame originale,
            # il merge basato sull'indice può fallire o dare risultati errati.
            # Per ora, presumiamo che gli indici siano allineabili o che AgGrid restituisca un DataFrame completo
            # che possa essere confrontato/usato per sostituire quello in session state.
            # Una strategia più sicura sarebbe usare un ID univoco per riga se disponibile, ma per ora usiamo l'indice.
            
            # Tentativo di aggiornare usando l'indice del df originale
            # Questo può essere problematico se gli indici non corrispondono più (es. dopo sort/filter in grid)
            # Un approccio più semplice ma potenzialmente meno performante:
            # st.session_state.processed_df = edited_df_from_grid_pd.copy()
            # Poi ricalcolare tutto. Per ora, proviamo l'aggiornamento selettivo.
            
            cols_editable_in_grid = ["nostro_prezzo", "shipping_cost"]
            if 'costo_acquisto' in current_df_display.columns: cols_editable_in_grid.append('costo_acquisto')
            
            changed_data = False
            # Crea una copia per le modifiche, preservando le colonne non editate
            df_to_be_updated = st.session_state.processed_df.copy()

            # Itera sulle righe del DataFrame ritornato dalla griglia
            # e aggiorna il DataFrame in session_state
            # Assumiamo che l'indice di edited_df_from_grid_pd corrisponda a quello originale
            # (o che sia un DataFrame completo che sostituisce quello vecchio)

            # Semplifichiamo: se la griglia restituisce dati, li usiamo come base per ricalcolare
            # Questo è più robusto ai cambi di indice/filtri nella griglia.
            
            # Confronto per vedere se i dati rilevanti sono cambiati
            current_relevant_cols = st.session_state.processed_df[cols_editable_in_grid]
            edited_relevant_cols = edited_df_from_grid_pd[cols_editable_in_grid]
            
            # Converti in numerico prima del confronto per coerenza
            for col in cols_editable_in_grid:
                current_relevant_cols[col] = pd.to_numeric(current_relevant_cols[col], errors='coerce')
                edited_relevant_cols[col] = pd.to_numeric(edited_relevant_cols[col], errors='coerce')

            if not current_relevant_cols.equals(edited_relevant_cols):
                logger.info("Grid data changed by user edit (based on relevant columns).")
                # Usa il df completo dalla griglia per ricalcolare
                # MA assicurati che tutte le colonne del df originale siano presenti, altrimenti il merge successivo potrebbe fallire
                # Copia le colonne non editabili dal df originale al df editato
                full_edited_df = st.session_state.processed_df.copy()
                for col_name in edited_df_from_grid_pd.columns:
                    if col_name in full_edited_df.columns:
                         # Applica le conversioni di tipo necessarie prima di assegnare
                        if col_name in cols_editable_in_grid:
                            full_edited_df[col_name] = pd.to_numeric(edited_df_from_grid_pd[col_name], errors='coerce')
                        else: # Per colonne non editabili, assumi che il tipo sia già corretto o prendilo com'è
                            full_edited_df[col_name] = edited_df_from_grid_pd[col_name]


                recalculated_df = pricing.update_all_calculated_columns(full_edited_df, float(st.session_state.last_fee_pct))
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
    st.info("📈 Carica il file Inserzioni Amazon per iniziare.")
elif not uploaded_keepa_files and uploaded_amazon_file:
     st.info("⬆️ File Amazon caricato. Ora carica i file Costi (opzionale) e Keepa, poi clicca 'Elabora Dati Principali'.")