import pandas as pd
from io import BytesIO, StringIO
from typing import Tuple, List, Dict, Any
from . import mapping # Import locale mapping utilities

class InvalidFileFormatError(ValueError):
    """Custom exception for invalid file formats or missing columns."""
    pass

def load_keepa_xlsx(uploaded_file: BytesIO) -> pd.DataFrame:
    """
    Loads data from a Keepa XLSX file.
    It expects specific column names from your Keepa export: 
    "ASIN", "Locale", "Buy Box: Current", "Categories: Root".

    Args:
        uploaded_file: The uploaded XLSX file object.

    Returns:
        A pandas DataFrame with Keepa data. Original column names like 
        "Buy Box: Current" and "Categories: Root" are preserved at this stage.
        Renaming happens later in app.py.
        
    Raises:
        InvalidFileFormatError: If required columns are missing.
    """
    try:
        df = pd.read_excel(uploaded_file)

        # Define the actual column names from your Keepa Excel export
        actual_asin_col_k = "ASIN"
        actual_locale_col_k = "Locale"
        actual_buybox_col_k = "Buy Box: Current" 
        actual_category_col_k = "Categories: Root"
        
        required_actual_cols_keepa = [
            actual_asin_col_k, 
            actual_locale_col_k, 
            actual_buybox_col_k, 
            actual_category_col_k
        ]
        
        missing_cols = [col for col in required_actual_cols_keepa if col not in df.columns]
        if missing_cols:
            expected_cols_msg = f"ASIN='{actual_asin_col_k}', Locale='{actual_locale_col_k}', BuyBox='{actual_buybox_col_k}', Category='{actual_category_col_k}'"
            raise InvalidFileFormatError(f"File Keepa ('{uploaded_file.name}'): Colonne mancanti. Attese: {expected_cols_msg}. Trovate: {', '.join(df.columns)}. Mancanti: {', '.join(missing_cols)}")
        
        # Standardize ASIN and Locale types/values
        if actual_asin_col_k in df.columns:
            df[actual_asin_col_k] = df[actual_asin_col_k].astype(str)
        if actual_locale_col_k in df.columns:
            df[actual_locale_col_k] = df[actual_locale_col_k].astype(str).str.lower()
        
        # The columns "Buy Box: Current" and "Categories: Root" will be renamed 
        # to "buybox_price" and "Category" respectively in app.py after all Keepa
        # files are loaded and concatenated.

        return df
    except Exception as e:
        if isinstance(e, InvalidFileFormatError):
            raise
        raise InvalidFileFormatError(f"File Keepa ('{uploaded_file.name}'): Errore durante la lettura del file Excel: {e}")


def load_amazon_csv(uploaded_file: BytesIO) -> Tuple[pd.DataFrame, List[str], Dict[str, Any]]:
    """
    Loads data from an Amazon Inserzioni CSV file.
    It expects specific column names from your CSV: "Codice(ASIN)" and "Prz.aggiornato".

    Args:
        uploaded_file: The uploaded CSV file object.

    Returns:
        A tuple containing:
            - df: pandas DataFrame with Amazon data. 
                  "Codice(ASIN)" is renamed to "Codice".
                  "Prz.aggiornato" is renamed to "nostro_prezzo".
            - original_columns: List of original column names.
            - original_dtypes: Dictionary of original column dtypes.
            
    Raises:
        InvalidFileFormatError: If required columns are missing or price cannot be converted.
    """
    try:
        try:
            content = uploaded_file.getvalue().decode('utf-8')
        except UnicodeDecodeError:
            uploaded_file.seek(0) # Reset buffer position
            content = uploaded_file.getvalue().decode('latin1')
        
        # Read the CSV
        df = pd.read_csv(StringIO(content), sep=';', decimal=',')
        
        original_columns = df.columns.tolist() # Store original column names before any renaming
        original_dtypes = df.dtypes.to_dict()

        # Define the actual column names from your CSV
        actual_asin_column_name = "Codice(ASIN)"
        actual_price_column_name = "Prz.aggiornato"
        # Other required columns (using their actual names from your CSV for checking)
        actual_sku_column_name = "SKU" # Assuming "SKU" is the actual name in your CSV
        actual_sito_column_name = "Sito" # Assuming "Sito" is the actual name in your CSV

        # Check for the presence of these actual column names
        required_actual_cols = [actual_sku_column_name, actual_asin_column_name, actual_sito_column_name, actual_price_column_name]
        missing_cols = [col for col in required_actual_cols if col not in df.columns]
        if missing_cols:
            expected_cols_message = f"SKU='{actual_sku_column_name}', ASIN='{actual_asin_column_name}', Sito='{actual_sito_column_name}', Prezzo='{actual_price_column_name}'"
            raise InvalidFileFormatError(f"File Inserzioni Amazon: Colonne mancanti. Attese: {expected_cols_message}. Trovate: {', '.join(df.columns)}. Mancanti: {', '.join(missing_cols)}")

        # Rename actual columns to internal standard names
        df.rename(columns={
            actual_asin_column_name: 'Codice', 
            actual_price_column_name: 'nostro_prezzo'
            # SKU and Sito are already standard if their actual names are "SKU" and "Sito"
        }, inplace=True)

        # Convert 'nostro_prezzo' to numeric
        if 'nostro_prezzo' in df.columns and df['nostro_prezzo'].dtype == 'object':
            # Remove potential thousands separators (like apostrophes in prices like "2'641,47")
            # and then convert comma decimal to dot decimal.
            df['nostro_prezzo'] = df['nostro_prezzo'].astype(str).str.replace("'", "", regex=False).str.replace(',', '.', regex=False)
            df['nostro_prezzo'] = pd.to_numeric(df['nostro_prezzo'], errors='coerce')

        # Ensure 'Codice' (ASIN) and 'Sito' are strings
        if 'Codice' in df.columns:
            df['Codice'] = df['Codice'].astype(str)
        if 'Sito' in df.columns: 
            df['Sito'] = df['Sito'].astype(str)

        return df, original_columns, original_dtypes
    except Exception as e:
        if isinstance(e, InvalidFileFormatError):
            raise
        raise InvalidFileFormatError(f"File Inserzioni Amazon: Errore durante la lettura del file CSV: {e}")


def extract_asins_for_keepa_search(amazon_df: pd.DataFrame) -> Dict[str, str]:
    """
    Extracts ASINs (from 'Codice' column) from the Amazon DataFrame,
    groups them by Keepa locale (mapped from 'Sito' column),
    and returns them as newline-separated strings.
    Assumes 'Codice' and 'Sito' columns exist after load_amazon_csv renaming.

    Args:
        amazon_df (pd.DataFrame): DataFrame from 'Inserzioni Amazon.CSV'. 
                                  Must contain 'Codice' and 'Sito' columns.

    Returns:
        Dict[str, str]: A dictionary where keys are Keepa locale codes (e.g., 'it', 'fr')
                        and values are newline-separated strings of unique ASINs for that locale.
                        Returns an empty dictionary if 'Codice' or 'Sito' are missing.
    """
    if 'Codice' not in amazon_df.columns or 'Sito' not in amazon_df.columns:
        return {}

    df_copy = amazon_df[['Codice', 'Sito']].copy()
    
    df_copy['Locale_Keepa'] = mapping.map_sito_to_locale_column(df_copy, 'Sito')
    
    df_copy = df_copy[df_copy['Locale_Keepa'].isin(mapping.LOCALE_TO_SITO_MAP.keys())]
    df_copy = df_copy.dropna(subset=['Codice'])
    df_copy = df_copy[df_copy['Codice'].str.strip() != '']

    asins_by_locale = df_copy.groupby('Locale_Keepa')['Codice'].apply(lambda x: '\n'.join(sorted(list(pd.Series(x).str.strip().unique()))))
    
    return asins_by_locale.to_dict()


def save_ready_pro_csv(df: pd.DataFrame, original_columns: List[str]) -> bytes:
    """
    Saves the DataFrame to a CSV string in Ready Pro format.
    Renames internal columns like 'nostro_prezzo' and 'Codice' back to their 
    original names as found in the input 'Inserzioni Amazon.CSV' for export.

    Args:
        df: The DataFrame to save. Must contain internal columns like 'nostro_prezzo'.
        original_columns: The list of original column names from 'Inserzioni Amazon.CSV'.

    Returns:
        bytes: The CSV data as bytes, encoded in UTF-8-BOM.
    """
    export_df = df.copy()
    
    # Determine the original price column name from the input CSV
    original_price_col_name_in_csv = "Prz.aggiornato" # As per user's CSV structure
    internal_price_col_name = "nostro_prezzo"

    if internal_price_col_name in export_df.columns and original_price_col_name_in_csv in original_columns:
        if internal_price_col_name != original_price_col_name_in_csv:
             export_df.rename(columns={internal_price_col_name: original_price_col_name_in_csv}, inplace=True)
    # Fallback if "Prz.aggiornato" wasn't somehow in original_columns but "Prezzo" was (legacy or different format)
    elif internal_price_col_name in export_df.columns and "Prezzo" in original_columns:
         export_df.rename(columns={internal_price_col_name: "Prezzo"}, inplace=True)
    
    
    # Determine the original ASIN column name from the input CSV
    original_asin_col_name_in_csv = "Codice(ASIN)" # As per user's CSV structure
    internal_asin_col_name = "Codice"

    if internal_asin_col_name in export_df.columns and original_asin_col_name_in_csv in original_columns:
        if internal_asin_col_name != original_asin_col_name_in_csv:
            export_df.rename(columns={internal_asin_col_name: original_asin_col_name_in_csv}, inplace=True)

    # Select only original columns in original order
    # This ensures the output CSV matches the input CSV's column structure and order.
    final_export_columns = []
    for col_name in original_columns:
        if col_name in export_df.columns:
            final_export_columns.append(col_name)
        # else: # If an original column is somehow missing from export_df, add it as empty
            # export_df[col_name] = pd.NA # Or some default

    export_df = export_df[final_export_columns]

    # Ensure the price column (whatever its original name was) is rounded to 2 decimal places
    price_col_for_rounding = original_price_col_name_in_csv if original_price_col_name_in_csv in export_df.columns else ("Prezzo" if "Prezzo" in export_df.columns else None)
    if price_col_for_rounding and export_df[price_col_for_rounding].dtype in ['float', 'float64']:
        export_df[price_col_for_rounding] = export_df[price_col_for_rounding].round(2)

    bytes_buffer = BytesIO()
    export_df.to_csv(bytes_buffer, sep=';', decimal=',', index=False, encoding='utf-8-sig')
    
    return bytes_buffer.getvalue()