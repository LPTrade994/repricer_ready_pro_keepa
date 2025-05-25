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
        required_cols = ['ASIN', 'Locale', 'BuyBox_Current', 'Category']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise InvalidFileFormatError(f"File Keepa ('{uploaded_file.name}'): Colonne mancanti: {', '.join(missing_cols)}")
        
        if 'ASIN' in df.columns:
            df['ASIN'] = df['ASIN'].astype(str)
        if 'Locale' in df.columns:
            df['Locale'] = df['Locale'].astype(str).str.lower() # Normalize locale to lowercase
        return df
    except Exception as e:
        if isinstance(e, InvalidFileFormatError):
            raise
        raise InvalidFileFormatError(f"File Keepa ('{uploaded_file.name}'): Errore durante la lettura del file Excel: {e}")


def load_amazon_csv(uploaded_file: BytesIO) -> Tuple[pd.DataFrame, List[str], Dict[str, Any]]:
    """
    Loads data from an Amazon Inserzioni CSV file.

    Args:
        uploaded_file: The uploaded CSV file object.

    Returns:
        A tuple containing:
            - df: pandas DataFrame with Amazon data. 'Prezzo' column is renamed to 'nostro_prezzo'.
            - original_columns: List of original column names.
            - original_dtypes: Dictionary of original column dtypes.
            
    Raises:
        InvalidFileFormatError: If required columns are missing or 'Prezzo' cannot be converted.
    """
    try:
        try:
            content = uploaded_file.getvalue().decode('utf-8')
        except UnicodeDecodeError:
            uploaded_file.seek(0)
            content = uploaded_file.getvalue().decode('latin1')
        
        df = pd.read_csv(StringIO(content), sep=';', decimal=',')
        
        original_columns = df.columns.tolist()
        original_dtypes = df.dtypes.to_dict()

        required_cols = ['SKU', 'Codice', 'Sito', 'Prezzo'] # Minimal set
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise InvalidFileFormatError(f"File Inserzioni Amazon: Colonne mancanti: {', '.join(missing_cols)}")

        if 'Prezzo' in df.columns:
            df.rename(columns={'Prezzo': 'nostro_prezzo'}, inplace=True)
            if df['nostro_prezzo'].dtype == 'object':
                df['nostro_prezzo'] = pd.to_numeric(df['nostro_prezzo'].astype(str).str.replace(',', '.', regex=False), errors='coerce')

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

    # Make a copy to avoid SettingWithCopyWarning
    df_copy = amazon_df[['Codice', 'Sito']].copy()
    
    # Map 'Sito' to Keepa 'Locale'
    df_copy['Locale_Keepa'] = mapping.map_sito_to_locale_column(df_copy, 'Sito')
    
    # Filter out rows where 'Locale_Keepa' is the same as 'Sito' (meaning no mapping found)
    # or where 'Codice' is NaN/empty
    df_copy = df_copy[df_copy['Locale_Keepa'].isin(mapping.LOCALE_TO_SITO_MAP.keys())]
    df_copy = df_copy.dropna(subset=['Codice'])
    df_copy = df_copy[df_copy['Codice'].str.strip() != '']


    # Group by 'Locale_Keepa' and aggregate unique 'Codice' (ASINs)
    asins_by_locale = df_copy.groupby('Locale_Keepa')['Codice'].apply(lambda x: '\n'.join(sorted(list(pd.Series(x).str.strip().unique()))))
    
    return asins_by_locale.to_dict()


def save_ready_pro_csv(df: pd.DataFrame, original_columns: List[str]) -> bytes:
    """
    Saves the DataFrame to a CSV string in Ready Pro format.

    Args:
        df: The DataFrame to save. Must contain 'nostro_prezzo' and other original columns.
        original_columns: The list of original column names in desired order.
                          'Prezzo' should be in this list where 'nostro_prezzo' existed.

    Returns:
        bytes: The CSV data as bytes, encoded in UTF-8-BOM.
    """
    export_df = df.copy()
    
    if 'nostro_prezzo' in export_df.columns and 'Prezzo' in original_columns:
        export_df.rename(columns={'nostro_prezzo': 'Prezzo'}, inplace=True)
    
    final_export_columns = []
    for col_name in original_columns:
        if col_name in export_df.columns:
            final_export_columns.append(col_name)

    export_df = export_df[final_export_columns]

    for col in export_df.select_dtypes(include=['float', 'float64']).columns:
        if col == 'Prezzo':
             export_df[col] = export_df[col].round(2)

    bytes_buffer = BytesIO()
    export_df.to_csv(bytes_buffer, sep=';', decimal=',', index=False, encoding='utf-8-sig')
    
    return bytes_buffer.getvalue()