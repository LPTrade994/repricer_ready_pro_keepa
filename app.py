import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode
import pandas as pd
import logging
from logging.handlers import TimedRotatingFileHandler
import yaml
from pathlib import Path

from services import io_layer, pricing, mapping

# --- Page Configuration ---
st.set_page_config(page_title="Repricer Ready Pro + Keepa", layout="wide")

# --- Logging Setup ---
LOG_FILE = "repricer.log"
logger = logging.getLogger("RepricerApp")
logger.setLevel(logging.INFO)
if not logger.handlers:
    # File handler for weekly rotation
    # Rotates every Monday (W0). backupCount can be adjusted for how many weeks of logs to keep.
    fh = TimedRotatingFileHandler(LOG_FILE, when="W0", interval=1, backupCount=4, encoding='utf-8')
    fh.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    # Console handler for streamlit logs
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)


# --- Configuration Loading ---
def load_app_config() -> dict:
    """Loads application configuration from YAML file."""
    try:
        with open(Path(__file__).parent / "config/amazon_fees.yml", "r") as f:
            config = yaml.safe_load(f)
        logger.info("Configuration loaded successfully.")
        return config
    except Exception as e:
        st.error(f"Error loading configuration: {e}")
        logger.error(f"Error loading configuration: {e}")
        return {"default_fee_pct": 15} # Fallback default

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


# --- UI Elements ---
st.title("🏷️ Repricer Ready Pro + Keepa")

with st.sidebar:
    st.header("📂 Caricamento File")
    keepa_file = st.file_uploader("Carica keepa.xlsx", type=["xlsx"])
    amazon_file = st.file_uploader("Carica Inserzioni Amazon.CSV", type=["csv"])

    st.header("⚙️ Impostazioni Globali")
    amazon_fee_pct_slider = st.slider(
        "Commissione Amazon (%)", 0, 100, 
        value=st.session_state.last_fee_pct, 
        key="amazon_fee_pct_slider_key"
    )
    
    st.session_state.last_fee_pct = amazon_fee_pct_slider

    process_button = st.button("🔄 Elabora Dati", disabled=not (keepa_file and amazon_file))

# --- Data Loading and Processing ---
if process_button and keepa_file and amazon_file:
    try:
        logger.info("Starting data processing.")
        st.session_state.amazon_filename = amazon_file.name

        amazon_df, original_cols, original_dtypes = io_layer.load_amazon_csv(amazon_file)
        st.session_state.original_amazon_columns = original_cols
        st.session_state.original_amazon_dtypes = original_dtypes
        logger.info(f"Amazon CSV loaded: {len(amazon_df)} rows.")

        keepa_df = io_layer.load_keepa_xlsx(keepa_file)
        logger.info(f"Keepa XLSX loaded: {len(keepa_df)} rows.")

        # Map Locale to Sito in Keepa data
        keepa_df['Sito_mapped'] = mapping.map_locale_to_sito_column(keepa_df, 'Locale')
        keepa_df.rename(columns={'BuyBox_Current': 'buybox_price'}, inplace=True)
        logger.info("Keepa data mapped and columns renamed.")
        
        # Merge data
        # Ensure 'Codice' in amazon_df and 'ASIN' in keepa_df are strings for reliable merging
        amazon_df['Codice'] = amazon_df['Codice'].astype(str)
        keepa_df['ASIN'] = keepa_df['ASIN'].astype(str)

        merged_df = pd.merge(
            amazon_df,
            keepa_df[['ASIN', 'Sito_mapped', 'buybox_price', 'Category']],
            left_on=['Codice', 'Sito'],
            right_on=['ASIN', 'Sito_mapped'],
            how='left'
        )
        # Drop redundant columns from keepa_df after merge if needed
        # merged_df.drop(columns=['ASIN_keepa_col', 'Sito_mapped_keepa_col'], inplace=True, errors='ignore')
        logger.info(f"Data merged: {len(merged_df)} rows.")

        # Initialize calculated columns
        merged_df['amazon_fee_pct_col'] = float(st.session_state.last_fee_pct)
        merged_df['shipping_cost'] = pricing.calculate_initial_shipping_cost(merged_df, 'Sito')
        
        # Convert nostro_prezzo and buybox_price to numeric, coercing errors
        merged_df['nostro_prezzo'] = pd.to_numeric(merged_df['nostro_prezzo'], errors='coerce')
        merged_df['buybox_price'] = pd.to_numeric(merged_df['buybox_price'], errors='coerce')

        merged_df = pricing.update_all_calculated_columns(merged_df, float(st.session_state.last_fee_pct))
        logger.info("Calculated columns initialized.")
        
        st.session_state.processed_df = merged_df.copy()
        st.success("Dati elaborati con successo!")
        # st.experimental_rerun() # Use st.rerun() for newer versions
        st.rerun()

    except io_layer.InvalidFileFormatError as e:
        st.error(f"Errore formato file: {e}")
        logger.error(f"InvalidFileFormatError: {e}")
        st.session_state.processed_df = None
    except Exception as e:
        st.error(f"Errore durante l'elaborazione: {e}")
        logger.error(f"Processing error: {e}", exc_info=True)
        st.session_state.processed_df = None


# --- Display and Interaction Area ---
if st.session_state.processed_df is not None:
    current_df = st.session_state.processed_df.copy()

    # Update amazon_fee_pct_col and recalculate if slider changed
    if float(st.session_state.last_fee_pct) != current_df['amazon_fee_pct_col'].iloc[0] if not current_df.empty else False :
        current_df['amazon_fee_pct_col'] = float(st.session_state.last_fee_pct)
        current_df = pricing.update_all_calculated_columns(current_df, float(st.session_state.last_fee_pct))
        st.session_state.processed_df = current_df.copy()
        # st.experimental_rerun()
        st.rerun()


    # --- AG-Grid Display ---
    gb = GridOptionsBuilder.from_dataframe(current_df)
    gb.configure_default_column(editable=False, resizable=True, sortable=True, filter=True)
    
    # Make specific columns editable
    gb.configure_column("nostro_prezzo", editable=True, type=["numericColumn", "numberColumnFilter", "customNumericFormat"], precision=2)
    gb.configure_column("shipping_cost", editable=True, type=["numericColumn", "numberColumnFilter", "customNumericFormat"], precision=2)

    # Configure selection
    gb.configure_selection(selection_mode="multiple", use_checkbox=True)

    # Conditional formatting for net_margin < 0
    js_row_style = JsCode("""
    function(params) {
        if (params.data.net_margin < 0) {
            return { 'background-color': '#FF7F7F' }; // Light red
        }
        return null;
    }""")
    gb.configure_grid_options(getRowStyle=js_row_style)
    
    # Custom formatting for currency columns (optional, AgGrid usually handles this with type numericColumn)
    currency_formatter = JsCode("""function(params) { return (params.value !== null && params.value !== undefined) ? parseFloat(params.value).toFixed(2) + ' €' : ''; }""")
    percentage_formatter = JsCode("""function(params) { return (params.value !== null && params.value !== undefined) ? parseFloat(params.value).toFixed(2) + ' %' : ''; }""")

    for col in ['buybox_price', 'diff_euro', 'nostro_prezzo', 'shipping_cost', 'net_margin']:
        if col in current_df.columns:
            gb.configure_column(col, valueFormatter=currency_formatter, type=["numericColumn", "numberColumnFilter"])
    
    if 'diff_pct' in current_df.columns:
        gb.configure_column('diff_pct', valueFormatter=percentage_formatter, type=["numericColumn", "numberColumnFilter"])


    gridOptions = gb.build()

    st.header("📊 Griglia Dati Editabile")
    grid_response = AgGrid(
        current_df,
        gridOptions=gridOptions,
        update_mode=GridUpdateMode.MODEL_CHANGED, # | GridUpdateMode.VALUE_CHANGED, # Send back data on cell edit
        fit_columns_on_grid_load=False,
        allow_unsafe_jscode=True,  # Set to True to allow JsCode.
        height=600,
        width='100%',
        # enable_enterprise_modules=True # if you have a license
    )

    edited_df_from_grid = grid_response['data']
    selected_rows = grid_response['selected_rows']

    if edited_df_from_grid is not None:
        edited_df_from_grid_pd = pd.DataFrame(edited_df_from_grid)
        # Ensure numeric types for edited columns
        for col in ['nostro_prezzo', 'shipping_cost']:
            if col in edited_df_from_grid_pd.columns:
                 edited_df_from_grid_pd[col] = pd.to_numeric(edited_df_from_grid_pd[col], errors='coerce')
        
        # Check if data actually changed to prevent infinite loops
        # Comparing all float columns can be tricky, use a tolerance or compare relevant ones
        # For simplicity, we assume a change if grid_response['data'] is not None and AgGrid was interacted with.
        # A more robust check would involve comparing st.session_state.processed_df with edited_df_from_grid_pd
        # if not st.session_state.processed_df.equals(edited_df_from_grid_pd): # This can be too strict for floats
        
        # Heuristic: If a known editable column has changed or selection happened, consider it an interaction
        # This part needs careful handling to avoid unnecessary recalculations / reruns.
        # Let's assume if model_changed, it needs update.
        
        # A simple check: if the dataframe from grid is different in shape or has different values for key columns
        # For now, we'll re-calculate if any cell was edited.
        # This typically happens when the user finishes editing a cell.
        
        # To avoid loop, we only update if actual values that pricing depends on changed.
        # Or, simpler: update if the dataframes differ significantly
        # Compare based on relevant columns changing
        cols_to_check = ['nostro_prezzo', 'shipping_cost']
        original_subset = st.session_state.processed_df[cols_to_check]
        edited_subset = edited_df_from_grid_pd[cols_to_check]

        if not original_subset.equals(edited_subset): # if relevant editable cols changed
            logger.info("Grid data changed by user edit.")
            recalculated_df = pricing.update_all_calculated_columns(edited_df_from_grid_pd, float(st.session_state.last_fee_pct))
            st.session_state.processed_df = recalculated_df.copy()
            # st.experimental_rerun()
            st.rerun()


    # --- Toolbar Actions ---
    st.header("🛠️ Azioni di Massa")
    if selected_rows:
        st.info(f"{len(selected_rows)} righe selezionate.")
        selected_indices = [row['_selectedRowNodeInfo']['nodeRowIndex'] for row in selected_rows]
    else:
        st.info("Nessuna riga selezionata. Seleziona le righe dalla griglia per azioni di massa.")
        selected_indices = []

    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("Scala Prezzo")
        scale_value = st.number_input("Valore Scala", value=0.0, step=0.01, format="%.2f")
        scale_type = st.radio("Tipo Scala", ["€", "%"], key="scale_type_radio")
        apply_scale = st.button("Applica Scala Prezzo", disabled=not selected_indices)

        if apply_scale and selected_indices:
            is_percentage = (scale_type == "%")
            df_after_scale = pricing.apply_scale_price(
                st.session_state.processed_df.copy(), 
                selected_indices, 
                scale_value, 
                is_percentage
            )
            df_after_scale = pricing.update_all_calculated_columns(df_after_scale, float(st.session_state.last_fee_pct))
            st.session_state.processed_df = df_after_scale
            logger.info(f"Applied 'Scala Prezzo' to {len(selected_indices)} rows.")
            # st.experimental_rerun()
            st.rerun()

    with col2:
        st.subheader("Allinea a Buy Box – Δ")
        delta_value = st.number_input("Valore Delta (Δ)", value=0.0, step=0.01, format="%.2f")
        delta_type = st.radio("Tipo Delta", ["€", "%"], key="delta_type_radio")
        apply_align = st.button("Applica Allineamento Buy Box", disabled=not selected_indices)

        if apply_align and selected_indices:
            is_percentage = (delta_type == "%")
            df_after_align = pricing.apply_align_to_buybox(
                st.session_state.processed_df.copy(),
                selected_indices,
                delta_value,
                is_percentage
            )
            df_after_align = pricing.update_all_calculated_columns(df_after_align, float(st.session_state.last_fee_pct))
            st.session_state.processed_df = df_after_align
            logger.info(f"Applied 'Allinea a Buy Box' to {len(selected_indices)} rows.")
            # st.experimental_rerun()
            st.rerun()
            
    with col3:
        st.subheader("Esporta")
        if st.button("💾 Esporta Ready Pro CSV"):
            try:
                output_csv_bytes = io_layer.save_ready_pro_csv(
                    st.session_state.processed_df,
                    st.session_state.original_amazon_columns,
                    # st.session_state.original_amazon_dtypes # Could be used for more precise type casting
                )
                
                export_filename = f"updated_{st.session_state.amazon_filename}"
                st.download_button(
                    label=f"Scarica {export_filename}",
                    data=output_csv_bytes,
                    file_name=export_filename,
                    mime="text/csv",
                )
                logger.info(f"Exported data to {export_filename}.")
                st.success(f"File {export_filename} pronto per il download.")
            except Exception as e:
                st.error(f"Errore durante l'esportazione: {e}")
                logger.error(f"Export error: {e}", exc_info=True)

else:
    st.info("📈 Carica i file Keepa e Inserzioni Amazon per iniziare.")