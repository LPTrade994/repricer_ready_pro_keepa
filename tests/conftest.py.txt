import pytest
import pandas as pd

@pytest.fixture
def sample_amazon_df() -> pd.DataFrame:
    """Provides a sample DataFrame mimicking Inserzioni Amazon.CSV content."""
    data = {
        'SKU': ['SKU001', 'SKU002', 'SKU003', 'SKU004'],
        'Codice': ['ASIN001', 'ASIN002', 'ASIN003', 'ASIN004'], # ASINs
        'Descrizione': ['Prodotto Italia 1', 'Prodotto Francia 1', 'Prodotto Italia 2', 'Prodotto Extra'],
        'Sito': ['Italia - Amazon.it', 'Francia - Amazon.fr', 'Italia - Amazon.it', 'Germania - Amazon.de'],
        'nostro_prezzo': [100.00, 200.50, 50.00, 75.00], # Already as float for testing pricing logic
        'Altra_Colonna': ['Val1', 'Val2', 'Val3', 'Val4']
    }
    df = pd.DataFrame(data)
    # Simulate that 'nostro_prezzo' might be loaded as object if original CSV had "100,00"
    # For pricing tests, we usually want it numeric. If testing io_layer, it would be string.
    # df['nostro_prezzo'] = df['nostro_prezzo'].astype(float) 
    return df

@pytest.fixture
def sample_merged_df() -> pd.DataFrame:
    """Provides a sample merged DataFrame for testing calculations."""
    data = {
        'SKU': ['SKU001', 'SKU002', 'SKU003', 'SKU004'],
        'Codice': ['ASIN001', 'ASIN002', 'ASIN003', 'ASIN004'],
        'Sito': ['Italia - Amazon.it', 'Francia - Amazon.fr', 'Italia - Amazon.it', 'Germania - Amazon.de'],
        'nostro_prezzo': [100.0, 150.0, 60.0, float('nan')], # One NaN price
        'buybox_price': [90.0, 160.0, float('nan'), 80.0], # One NaN buybox
        'shipping_cost': [5.14, 11.50, 5.14, 11.50],
        'amazon_fee_pct_col': [15.0, 15.0, 15.0, 15.0],
        'Category': ['Elettronica', 'Libri', 'Elettronica', 'Casa']
    }
    return pd.DataFrame(data)