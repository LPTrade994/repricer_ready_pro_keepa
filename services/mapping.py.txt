import pandas as pd

LOCALE_TO_SITO_MAP = {
    'it': 'Italia - Amazon.it',
    'fr': 'Francia - Amazon.fr',
    'de': 'Germania - Amazon.de',
    'es': 'Spagna - Amazon.es',
    'nl': 'Paesi bassi - Amazon.nl',
    'be': 'Belgio - Amazon.com.be', # Note: Prompt says Amazon.com.be, typically it's Amazon.com.be or Amazon.be
    'ie': 'Irlanda - Amazon.ie',
    'se': 'Svezia - Amazon.se'
}

def map_locale_to_sito(locale_code: str) -> str:
    """
    Maps a locale code (e.g., 'it') to its corresponding Amazon Sito string.

    Args:
        locale_code (str): The locale code.

    Returns:
        str: The Amazon Sito string, or the original code if not found.
    """
    return LOCALE_TO_SITO_MAP.get(str(locale_code).lower(), str(locale_code))


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