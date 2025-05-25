import pandas as pd
from io import BytesIO, StringIO
from typing import Tuple, List, Dict, Any

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
            raise InvalidFileFormatError(f"File Keepa: Colonne mancanti: {', '.join(missing_cols)}")
        
        # Ensure ASIN is string
        if 'ASIN' in df.columns:
            df['ASIN'] = df['ASIN'].astype(str)
        return df
    except Exception as e:
        if isinstance(e, InvalidFileFormatError):
            raise
        raise InvalidFileFormatError(f"File Keepa: Errore durante la lettura del file Excel: {e}")


def load_amazon_csv(uploaded_file: BytesIO) -> Tuple[pd.DataFrame, List[str], Dict[str, Any]]:
    """
    Loads data from an Amazon Inserzioni CSV file.

    Args:
        uploaded_file: The uploaded CSV file object.

    Returns:
        A tuple containing:
            - df: pandas DataFrame with Amazon data. 'Prezzo' column is renamed to 'nostro_prezzo' and converted to float.
            - original_columns: List of original column names.
            - original_dtypes: Dictionary of original column dtypes.
            
    Raises:
        InvalidFileFormatError: If required columns are missing or 'Prezzo' cannot be converted.
    """
    try:
        # Read the content of the uploaded file, try UTF-8 first, then latin1 as fallback
        try:
            content = uploaded_file.getvalue().decode('utf-8')
        except UnicodeDecodeError:
            uploaded_file.seek(0) # Reset buffer position
            content = uploaded_file.getvalue().decode('latin1') # Common for some CSV exports
        
        df = pd.read_csv(StringIO(content), sep=';', decimal=',') # Assuming EU decimal format for Prezzo
        
        original_columns = df.columns.tolist()
        original_dtypes = df.dtypes.to_dict()

        required_cols = ['SKU', 'Codice', 'Descrizione', 'Sito', 'Prezzo'] # Minimal set
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise InvalidFileFormatError(f"File Inserzioni Amazon: Colonne mancanti: {', '.join(missing_cols)}")

        # Rename Prezzo and ensure it's numeric
        if 'Prezzo' in df.columns:
            df.rename(columns={'Prezzo': 'nostro_prezzo'}, inplace=True)
            # 'nostro_prezzo' should already be float due to decimal=',' in read_csv.
            # If it's object, it means there were non-numeric values.
            if df['nostro_prezzo'].dtype == 'object':
                 # Attempt conversion again, forcing errors to NaN
                df['nostro_prezzo'] = pd.to_numeric(df['nostro_prezzo'].astype(str).str.replace(',', '.', regex=False), errors='coerce')
                if df['nostro_prezzo'].isnull().any(): # Check if any NaN produced by non-numeric
                    # This warning can be enhanced to pinpoint problematic rows if necessary
                    # logger.warning("Some 'Prezzo' values in Amazon CSV were not numeric and are now NaN.")
                    pass # Allow NaN and handle in logic

        # Ensure Codice is string
        if 'Codice' in df.columns:
            df['Codice'] = df['Codice'].astype(str)

        return df, original_columns, original_dtypes
    except Exception as e:
        if isinstance(e, InvalidFileFormatError):
            raise
        raise InvalidFileFormatError(f"File Inserzioni Amazon: Errore durante la lettura del file CSV: {e}")


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
    
    # Rename 'nostro_prezzo' back to 'Prezzo' for export
    if 'nostro_prezzo' in export_df.columns and 'Prezzo' in original_columns:
        export_df.rename(columns={'nostro_prezzo': 'Prezzo'}, inplace=True)
    
    # Select only original columns in original order
    # Ensure all original columns are present, fill missing ones with NaN or default if any somehow got lost
    final_export_columns = []
    for col_name in original_columns:
        if col_name in export_df.columns:
            final_export_columns.append(col_name)
        # else: # If a column is critical and missing, this is a place to handle it
            # export_df[col_name] = pd.NA # or some default

    export_df = export_df[final_export_columns]

    # Ensure 'Prezzo' and other potential float columns are rounded to 2 decimal places
    # This is a general approach; more specific dtype handling could be added using original_dtypes
    for col in export_df.select_dtypes(include=['float', 'float64']).columns:
        if col == 'Prezzo': # Specific handling for Prezzo
             export_df[col] = export_df[col].round(2)
        # else: # Other float columns might need different rounding or no rounding
            # export_df[col] = export_df[col].round(some_other_precision)


    # Use StringIO to build CSV string, then encode
    csv_buffer = StringIO()
    export_df.to_csv(csv_buffer, sep=';', decimal=',', index=False, encoding='utf-8')
    
    # Prepend BOM for UTF-8-SIG
    # The 'utf-8-sig' encoding in to_csv directly handles BOM
    # If to_csv used 'utf-8', then manual BOM prepending would be:
    # csv_string = '\ufeff' + csv_buffer.getvalue()
    # return csv_string.encode('utf-8')
    
    # Using 'utf-8-sig' directly with BytesIO
    bytes_buffer = BytesIO()
    export_df.to_csv(bytes_buffer, sep=';', decimal=',', index=False, encoding='utf-8-sig')
    
    return bytes_buffer.getvalue()