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

    Args:
        uploaded_file: The uploaded XLSX file object.

    Returns:
        A pandas DataFrame with Keepa data.
        
    Raises:
        InvalidFileFormatError: If required columns are missing.
    """
    try:
        df = pd.read_excel(uploaded_file)
        required_cols_keepa = ['ASIN', 'Locale', 'BuyBox_Current', 'Category'] # Specific for Keepa
        missing_cols = [col for col in required_cols_keepa if col not in df.columns]
        if missing_cols:
            raise InvalidFileFormatError(f"File Keepa ('{uploaded_file.name}'): Colonne mancanti: {', '.join(missing_cols)}")
        
        if 'ASIN' in df.columns:
            df['ASIN'] = df['ASIN'].astype(str)
        if 'Locale' in df.columns:
            df['Locale'] = df['Locale'].astype(str).str.lower()
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
            uploaded_file.seek(0)
            content = uploaded_file.getvalue().decode('latin1')
        
        # Read the CSV
        df = pd.read_csv(StringIO(content), sep=';', decimal=',')
        
        original_columns = df.columns.tolist() # Store original column names before any renaming
        original_dtypes = df.dtypes.to_dict()

        # Define the actual column names from your CSV
        actual_asin_column_name = "Codice(ASIN)"
        actual_price_column_name = "Prz.aggiornato"
        # Other required columns (standardized names used internally)
        internal_sku_column_name = "SKU" # Assuming "SKU" is the actual name in your CSV
        internal_sito_column_name = "Sito" # Assuming "Sito" is the actual name in your CSV

        # Check for the presence of these actual column names
        required_actual_cols = [internal_sku_column_name, actual_asin_column_name, internal_sito_column_name, actual_price_column_name]
        missing_cols = [col for col in required_actual_cols if col not in df.columns]
        if missing_cols:
            # Provide a more informative error message about the expected actual column names
            expected_cols_message = f"SKU='{internal_sku_column_name}', ASIN='{actual_asin_column_name}', Sito='{internal_sito_column_name}', Prezzo='{actual_price_column_name}'"
            raise InvalidFileFormatError(f"File Inserzioni Amazon: Colonne mancanti. Attese: {expected_cols_message}. Trovate: {', '.join(df.columns)}. Mancanti: {', '.join(missing_cols)}")

        # Rename actual columns to internal standard names
        df.rename(columns={
            actual_asin_column_name: 'Codice', 
            actual_price_column_name: 'nostro_prezzo'
        }, inplace=True)

        # Convert 'nostro_prezzo' to numeric
        if df['nostro_prezzo'].dtype == 'object':
            # Remove potential thousands separators (like apostrophes in prices like "2'641,47")
            df['nostro_prezzo'] = df['nostro_prezzo'].astype(str).str.replace("'", "", regex=False).str.replace(',', '.', regex=False)
            df['nostro_prezzo'] = pd.to_numeric(df['nostro_prezzo'], errors='coerce')

        # Ensure 'Codice' (ASIN) and 'Sito' are strings
        if 'Codice' in df.columns:
            df['Codice'] = df['Codice'].astype(str)
        if 'Sito' in df.columns: # 'Sito' is already one of our internal names
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
        # This should not happen if load_amazon_csv ran successfully
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
    Renames internal 'nostro_prezzo' back to its original name in the export CSV
    if the original price column name was different (e.g., "Prz.aggiornato").

    Args:
        df: The DataFrame to save. Must contain 'nostro_prezzo' and other original columns.
        original_columns: The list of original column names in desired order.
                          The original price column name (e.g., "Prz.aggiornato") should be in this list.

    Returns:
        bytes: The CSV data as bytes, encoded in UTF-8-BOM.
    """
    export_df = df.copy()
    
    # Determine the original price column name.
    # This logic assumes that if "Prz.aggiornato" was in original_columns, it was the price.
    # A more robust way might be to store the original name of the price column during load.
    # For now, let's assume if "Prezzo" is not in original_columns, but "Prz.aggiornato" is, use that.
    original_price_col_name = "Prezzo" # Default
    if "Prz.aggiornato" in original_columns:
        original_price_col_name = "Prz.aggiornato"
    elif "Prezzo" not in original_columns and any("Prz" in col for col in original_columns):
        # Heuristic: find a column with "Prz" if "Prezzo" or "Prz.aggiornato" aren't explicitly there.
        # This part can be risky and might need refinement based on actual CSV variations.
        potential_price_cols = [col for col in original_columns if "Prz" in col]
        if potential_price_cols:
            original_price_col_name = potential_price_cols[0] # Take the first match

    if 'nostro_prezzo' in export_df.columns and original_price_col_name in original_columns:
        export_df.rename(columns={'nostro_prezzo': original_price_col_name}, inplace=True)
    elif 'nostro_prezzo' in export_df.columns and 'Prezzo' in original_columns: # Fallback if dynamic renaming failed
         export_df.rename(columns={'nostro_prezzo': 'Prezzo'}, inplace=True)
    
    
    # Rename 'Codice' back to 'Codice(ASIN)' if that was the original
    original_asin_col_name = "Codice" # Default
    if "Codice(ASIN)" in original_columns:
        original_asin_col_name = "Codice(ASIN)"

    if 'Codice' in export_df.columns and original_asin_col_name in original_columns and 'Codice' != original_asin_col_name:
        export_df.rename(columns={'Codice': original_asin_col_name}, inplace=True)


    # Select only original columns in original order
    # Make sure all original columns are present for the export
    final_export_columns = []
    for col_name in original_columns:
        if col_name in export_df.columns:
            final_export_columns.append(col_name)
        # else: # If a column is critical and missing (should not happen if logic is correct)
            # export_df[col_name] = pd.NA 

    export_df = export_df[final_export_columns]

    # Ensure the price column (whatever its original name was) is rounded to 2 decimal places
    if original_price_col_name in export_df.columns and export_df[original_price_col_name].dtype in ['float', 'float64']:
        export_df[original_price_col_name] = export_df[original_price_col_name].round(2)
    # Also round other float columns if necessary, but be careful not to over-round non-currency floats.
    # for col in export_df.select_dtypes(include=['float', 'float64']).columns:
    #     if col != original_price_col_name: # Example: don't re-round price if already handled
    #         # export_df[col] = export_df[col].round(some_other_precision_if_needed)
    #         pass


    bytes_buffer = BytesIO()
    export_df.to_csv(bytes_buffer, sep=';', decimal=',', index=False, encoding='utf-8-sig')
    
    return bytes_buffer.getvalue()