import pandas as pd

LOCALE_TO_SITO_MAP = {
    'it': 'Italia - Amazon.it',
    'fr': 'Francia - Amazon.fr',
    'de': 'Germania - Amazon.de',
    'es': 'Spagna - Amazon.es',
    'nl': 'Paesi bassi - Amazon.nl',
    'be': 'Belgio - Amazon.com.be',
    'ie': 'Irlanda - Amazon.ie',
    'se': 'Svezia - Amazon.se'
}

# Mappa inversa per SITO -> LOCALE
SITO_TO_LOCALE_MAP = {v: k for k, v in LOCALE_TO_SITO_MAP.items()}

def map_locale_to_sito(locale_code: str) -> str:
    """
    Maps a locale code (e.g., 'it') to its corresponding Amazon Sito string.

    Args:
        locale_code (str): The locale code.

    Returns:
        str: The Amazon Sito string, or the original code if not found.
    """
    return LOCALE_TO_SITO_MAP.get(str(locale_code).lower(), str(locale_code))

def map_sito_to_locale(sito_string: str) -> str:
    """
    Maps an Amazon Sito string (e.g., 'Italia - Amazon.it') to its corresponding locale code.

    Args:
        sito_string (str): The Amazon Sito string.

    Returns:
        str: The locale code, or the original Sito string if not found.
    """
    return SITO_TO_LOCALE_MAP.get(sito_string, sito_string)


def map_locale_to_sito_column(df: pd.DataFrame, locale_column_name: str) -> pd.Series:
    """
    Applies locale_to_sito mapping to a DataFrame column.

    Args:
        df (pd.DataFrame): The DataFrame.
        locale_column_name (str): The name of the column containing locale codes.

    Returns:
        pd.Series: A new Series with mapped Sito strings.
    """
    if locale_column_name not in df.columns:
        raise KeyError(f"Colonna '{locale_column_name}' non trovata nel DataFrame.")
    return df[locale_column_name].astype(str).apply(map_locale_to_sito)

def map_sito_to_locale_column(df: pd.DataFrame, sito_column_name: str) -> pd.Series:
    """
    Applies sito_to_locale mapping to a DataFrame column.

    Args:
        df (pd.DataFrame): The DataFrame.
        sito_column_name (str): The name of the column containing Sito strings.

    Returns:
        pd.Series: A new Series with mapped locale codes.
    """
    if sito_column_name not in df.columns:
        raise KeyError(f"Colonna '{sito_column_name}' non trovata nel DataFrame.")
    return df[sito_column_name].astype(str).apply(map_sito_to_locale)