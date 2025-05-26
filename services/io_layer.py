import pandas as pd
from io import BytesIO, StringIO
from typing import Tuple, List, Dict, Any
from . import mapping # Import locale mapping utilities

class InvalidFileFormatError(ValueError):
    """Custom exception for invalid file formats or missing columns."""
    pass

def load_cost_csv(uploaded_file: BytesIO) -> pd.DataFrame:
    """
    Loads data from the product cost CSV file.
    Expected columns: "Codice" (maps to SKU) and "Prezzo medio" (maps to costo_acquisto).

    Args:
        uploaded_file: The uploaded CSV file object.

    Returns:
        A pandas DataFrame with product costs.
        
    Raises:
        InvalidFileFormatError: If required columns are missing or price cannot be converted.
    """
    try:
        try:
            content = uploaded_file.getvalue().decode('utf-8-sig')
        except UnicodeDecodeError:
            uploaded_file.seek(0)
            try:
                content = uploaded_file.getvalue().decode('utf-8')
            except UnicodeDecodeError:
                uploaded_file.seek(0)
                content = uploaded_file.getvalue().decode('latin1')
        
        df = pd.read_csv(StringIO(content), sep=';', decimal=',')
        
        actual_sku_col_cost = "Codice" 
        actual_cost_price_col = "Prezzo medio"
        
        required_cols_cost = [actual_sku_col_cost, actual_cost_price_col]
        missing_cols = [col for col in required_cols_cost if col not in df.columns]

        if missing_cols:
            expected_cols_msg = f"Codice_SKU='{actual_sku_col_cost}', Prezzo_Costo='{actual_cost_price_col}'"
            raise InvalidFileFormatError(f"File Costi Prodotto ('{uploaded_file.name}'): Colonne mancanti. Attese: {expected_cols_msg}. Trovate: {', '.join(df.columns)}. Mancanti: {', '.join(missing_cols)}")

        df.rename(columns={
            actual_sku_col_cost: 'SKU_cost', 
            actual_cost_price_col: 'costo_acquisto'
        }, inplace=True)

        if 'costo_acquisto' in df.columns and df['costo_acquisto'].dtype == 'object':
            df['costo_acquisto'] = df['costo_acquisto'].astype(str).str.replace("'", "", regex=False).str.replace(',', '.', regex=False)
            df['costo_acquisto'] = pd.to_numeric(df['costo_acquisto'], errors='coerce')
        
        if 'SKU_cost' in df.columns:
            df['SKU_cost'] = df['SKU_cost'].astype(str)
            
        df.drop_duplicates(subset=['SKU_cost'], keep='first', inplace=True)

        return df
    except Exception as e:
        if isinstance(e, InvalidFileFormatError):
            raise
        raise InvalidFileFormatError(f"File Costi Prodotto ('{uploaded_file.name}'): Errore durante la lettura: {e}")


def load_keepa_xlsx(uploaded_file: BytesIO) -> pd.DataFrame:
    """
    Loads data from a Keepa XLSX file.
    Expected column names: "ASIN", "Locale", "Buy Box: Current", "Categories: Root".
    """
    try:
        df = pd.read_excel(uploaded_file)
        actual_asin_col_k = "ASIN"
        actual_locale_col_k = "Locale"
        actual_buybox_col_k_excel = "Buy Box: Current" 
        actual_category_col_k_excel = "Categories: Root"
        required_actual_cols_keepa = [actual_asin_col_k, actual_locale_col_k, actual_buybox_col_k_excel, actual_category_col_k_excel]
        missing_cols = [col for col in required_actual_cols_keepa if col not in df.columns]
        if missing_cols:
            expected_cols_msg = f"ASIN='{actual_asin_col_k}', Locale='{actual_locale_col_k}', BuyBox='{actual_buybox_col_k_excel}', Category='{actual_category_col_k_excel}'"
            raise InvalidFileFormatError(f"File Keepa Excel ('{uploaded_file.name}'): Colonne mancanti. Attese: {expected_cols_msg}. Trovate: {', '.join(df.columns)}. Mancanti: {', '.join(missing_cols)}")
        if actual_asin_col_k in df.columns: df[actual_asin_col_k] = df[actual_asin_col_k].astype(str)
        if actual_locale_col_k in df.columns: df[actual_locale_col_k] = df[actual_locale_col_k].astype(str).str.lower()
        return df
    except Exception as e:
        if isinstance(e, InvalidFileFormatError): raise
        raise InvalidFileFormatError(f"File Keepa Excel ('{uploaded_file.name}'): Errore durante la lettura del file Excel: {e}")


def load_keepa_csv(uploaded_file: BytesIO) -> pd.DataFrame:
    """
    Loads data from a Keepa CSV file.
    Expected column names: "Locale", "ASIN", "Buy Box 🚚: Corrente", "Gruppo di visualizzazione del sito web: Nome".
    """
    try:
        try: content = uploaded_file.getvalue().decode('utf-8-sig') 
        except UnicodeDecodeError:
            uploaded_file.seek(0)
            try: content = uploaded_file.getvalue().decode('utf-8')
            except UnicodeDecodeError:
                uploaded_file.seek(0)
                content = uploaded_file.getvalue().decode('latin1')
        df = pd.read_csv(StringIO(content), sep=',') 
        actual_locale_col_k_csv = "Locale" 
        if f"{chr(65279)}Locale" in df.columns: 
            actual_locale_col_k_csv = f"{chr(65279)}Locale"
            df.rename(columns={actual_locale_col_k_csv: "Locale"}, inplace=True)
            actual_locale_col_k_csv = "Locale"
        elif "Locale" not in df.columns and len(df.columns) > 0 and df.columns[0].endswith("Locale"):
            if df.columns[0] != "Locale": df.rename(columns={df.columns[0]: "Locale"}, inplace=True)
            actual_locale_col_k_csv = "Locale"
        actual_asin_col_k_csv = "ASIN"
        actual_buybox_col_k_csv = "Buy Box 🚚: Corrente" 
        actual_category_col_k_csv = "Gruppo di visualizzazione del sito web: Nome"
        required_actual_cols_keepa_csv = [actual_locale_col_k_csv, actual_asin_col_k_csv, actual_buybox_col_k_csv, actual_category_col_k_csv]
        missing_cols = [col for col in required_actual_cols_keepa_csv if col not in df.columns]
        if missing_cols:
            expected_cols_msg = f"Locale='{actual_locale_col_k_csv}', ASIN='{actual_asin_col_k_csv}', BuyBox='{actual_buybox_col_k_csv}', Categoria='{actual_category_col_k_csv}'"
            raise InvalidFileFormatError(f"File Keepa CSV ('{uploaded_file.name}'): Colonne mancanti. Attese: {expected_cols_msg}. Colonne trovate: {', '.join(df.columns)}. Mancanti: {', '.join(missing_cols)}")
        if actual_asin_col_k_csv in df.columns: df[actual_asin_col_k_csv] = df[actual_asin_col_k_csv].astype(str)
        if "Locale" in df.columns: df["Locale"] = df["Locale"].astype(str).str.lower()
        return df
    except Exception as e:
        if isinstance(e, InvalidFileFormatError): raise
        raise InvalidFileFormatError(f"File Keepa CSV ('{uploaded_file.name}'): Errore durante la lettura: {e}")


def load_amazon_csv(uploaded_file: BytesIO) -> Tuple[pd.DataFrame, List[str], Dict[str, Any]]:
    try:
        try: content = uploaded_file.getvalue().decode('utf-8')
        except UnicodeDecodeError:
            uploaded_file.seek(0); content = uploaded_file.getvalue().decode('latin1')
        df = pd.read_csv(StringIO(content), sep=';', decimal=',')
        original_columns = df.columns.tolist()
        original_dtypes = df.dtypes.to_dict()
        actual_asin_column_name = "Codice(ASIN)"
        actual_price_column_name = "Prz.aggiornato"
        actual_sku_column_name = "SKU"
        actual_sito_column_name = "Sito"
        required_actual_cols = [actual_sku_column_name, actual_asin_column_name, actual_sito_column_name, actual_price_column_name]
        missing_cols = [col for col in required_actual_cols if col not in df.columns]
        if missing_cols:
            expected_cols_message = f"SKU='{actual_sku_column_name}', ASIN='{actual_asin_column_name}', Sito='{actual_sito_column_name}', Prezzo='{actual_price_column_name}'"
            raise InvalidFileFormatError(f"File Inserzioni Amazon: Colonne mancanti. Attese: {expected_cols_message}. Trovate: {', '.join(df.columns)}. Mancanti: {', '.join(missing_cols)}")
        df.rename(columns={actual_asin_column_name: 'Codice', actual_price_column_name: 'nostro_prezzo'}, inplace=True)
        if 'nostro_prezzo' in df.columns and df['nostro_prezzo'].dtype == 'object':
            df['nostro_prezzo'] = df['nostro_prezzo'].astype(str).str.replace("'", "", regex=False).str.replace(',', '.', regex=False)
            df['nostro_prezzo'] = pd.to_numeric(df['nostro_prezzo'], errors='coerce')
        if 'Codice' in df.columns: df['Codice'] = df['Codice'].astype(str)
        if 'Sito' in df.columns: df['Sito'] = df['Sito'].astype(str)
        return df, original_columns, original_dtypes
    except Exception as e:
        if isinstance(e, InvalidFileFormatError): raise
        raise InvalidFileFormatError(f"File Inserzioni Amazon: Errore lettura CSV: {e}")


def extract_asins_for_keepa_search(amazon_df: pd.DataFrame) -> Dict[str, str]:
    if 'Codice' not in amazon_df.columns or 'Sito' not in amazon_df.columns: return {}
    df_copy = amazon_df[['Codice', 'Sito']].copy()
    df_copy['Locale_Keepa'] = mapping.map_sito_to_locale_column(df_copy, 'Sito')
    df_copy = df_copy[df_copy['Locale_Keepa'].isin(mapping.LOCALE_TO_SITO_MAP.keys())]
    df_copy = df_copy.dropna(subset=['Codice'])
    df_copy = df_copy[df_copy['Codice'].str.strip() != '']
    asins_by_locale = df_copy.groupby('Locale_Keepa')['Codice'].apply(lambda x: '\n'.join(sorted(list(pd.Series(x).str.strip().unique()))))
    return asins_by_locale.to_dict()


def save_ready_pro_csv(df: pd.DataFrame, original_columns: List[str]) -> bytes:
    export_df = df.copy()
    original_price_col_name_in_csv = "Prz.aggiornato"
    internal_price_col_name = "nostro_prezzo"
    if internal_price_col_name in export_df.columns and original_price_col_name_in_csv in original_columns:
        if internal_price_col_name != original_price_col_name_in_csv:
             export_df.rename(columns={internal_price_col_name: original_price_col_name_in_csv}, inplace=True)
    elif internal_price_col_name in export_df.columns and "Prezzo" in original_columns:
         export_df.rename(columns={internal_price_col_name: "Prezzo"}, inplace=True)
    original_asin_col_name_in_csv = "Codice(ASIN)"
    internal_asin_col_name = "Codice"
    if internal_asin_col_name in export_df.columns and original_asin_col_name_in_csv in original_columns:
        if internal_asin_col_name != original_asin_col_name_in_csv:
            export_df.rename(columns={internal_asin_col_name: original_asin_col_name_in_csv}, inplace=True)
    final_export_columns = []
    for col_name in original_columns:
        if col_name in export_df.columns:
            final_export_columns.append(col_name)
    export_df = export_df[final_export_columns]
    price_col_for_rounding = original_price_col_name_in_csv if original_price_col_name_in_csv in export_df.columns else ("Prezzo" if "Prezzo" in export_df.columns else None)
    if price_col_for_rounding and export_df[price_col_for_rounding].dtype in ['float', 'float64']:
        export_df[price_col_for_rounding] = export_df[price_col_for_rounding].round(2)
    bytes_buffer = BytesIO()
    export_df.to_csv(bytes_buffer, sep=';', decimal=',', index=False, encoding='utf-8-sig')
    return bytes_buffer.getvalue()