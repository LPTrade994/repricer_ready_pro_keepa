import pandas as pd
import numpy as np
from typing import List, Tuple, Optional
import re
from . import mapping # Assicurati che mapping.py sia accessibile

def calculate_initial_shipping_cost(df: pd.DataFrame, sito_column_name: str = 'Sito') -> pd.Series:
    """Calculates initial shipping cost based on the 'Sito' column."""
    return pd.Series(np.where(df[sito_column_name].astype(str).str.contains('Italia', case=False, na=False), 5.14, 11.50), index=df.index)

def calculate_diffs(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
    """Calculates diff_euro and diff_pct."""
    nostro_prezzo_numeric = pd.to_numeric(df['nostro_prezzo'], errors='coerce')
    buybox_price_numeric = pd.to_numeric(df['buybox_price'], errors='coerce')
    diff_euro = buybox_price_numeric - nostro_prezzo_numeric
    diff_pct = pd.Series(index=df.index, dtype='float64')
    valid_prices_mask = (nostro_prezzo_numeric.notna()) & (nostro_prezzo_numeric != 0) & (buybox_price_numeric.notna())
    diff_pct.loc[valid_prices_mask] = (buybox_price_numeric.loc[valid_prices_mask] / nostro_prezzo_numeric.loc[valid_prices_mask] - 1) * 100
    return diff_euro.round(2), diff_pct.round(2)

def parse_fee_string(fee_str: str) -> Optional[float]:
    """Parses a fee string and returns the first percentage found."""
    if pd.isna(fee_str) or not isinstance(fee_str, str): return None
    match = re.search(r"(\d+(\.\d+)?)\s*%", fee_str)
    if match:
        try: return float(match.group(1))
        except ValueError: return None
    return None

def get_amazon_fee_pct_for_row(row: pd.Series, 
                               amazon_fees_df: Optional[pd.DataFrame], 
                               default_fee_pct: float) -> float:
    """Determines the Amazon fee percentage for a row."""
    if amazon_fees_df is None or amazon_fees_df.empty: return default_fee_pct
    selected_category = row.get('amazon_category_selected'); sito = row.get('Sito')
    if pd.isna(selected_category) or selected_category == "" or pd.isna(sito): return default_fee_pct
    fee_column_name = mapping.map_sito_to_fee_column_name(sito)
    if not fee_column_name or fee_column_name not in amazon_fees_df.columns: return default_fee_pct
    try:
        fee_string = amazon_fees_df.loc[selected_category, fee_column_name]
        parsed_fee = parse_fee_string(fee_string)
        return parsed_fee if parsed_fee is not None else default_fee_pct
    except KeyError: return default_fee_pct
    except Exception: return default_fee_pct

def calculate_net_margin(df: pd.DataFrame) -> pd.Series:
    """Calculates net_margin using per-row amazon_fee_pct_col."""
    nostro_prezzo_numeric = pd.to_numeric(df['nostro_prezzo'], errors='coerce')
    shipping_cost_numeric = pd.to_numeric(df['shipping_cost'], errors='coerce')
    costo_acquisto_numeric = pd.to_numeric(df['costo_acquisto'], errors='coerce').fillna(0)
    fee_pct_series = pd.to_numeric(df['amazon_fee_pct_col'], errors='coerce').fillna(0) / 100.0 # FillNa with 0 if fee is not found
    amazon_fee_amount = nostro_prezzo_numeric * fee_pct_series
    net_margin = nostro_prezzo_numeric - amazon_fee_amount - shipping_cost_numeric - costo_acquisto_numeric
    return net_margin.round(2)

def update_all_calculated_columns(df: pd.DataFrame, 
                                  amazon_fees_data: Optional[pd.DataFrame], 
                                  global_default_fee_pct: float) -> pd.DataFrame:
    """Updates all calculated columns including the dynamic amazon_fee_pct_col."""
    df_updated = df.copy()
    for col in ['nostro_prezzo', 'buybox_price', 'shipping_cost', 'costo_acquisto']:
        if col in df_updated.columns: df_updated[col] = pd.to_numeric(df_updated[col], errors='coerce')
        elif col == 'costo_acquisto': df_updated[col] = 0.0 
    if 'costo_acquisto' in df_updated.columns: df_updated['costo_acquisto'].fillna(0, inplace=True)
    else: df_updated['costo_acquisto'] = 0.0
    if 'amazon_category_selected' not in df_updated.columns: df_updated['amazon_category_selected'] = "" # Ensure column exists
    
    df_updated['amazon_fee_pct_col'] = df_updated.apply(
        lambda row: get_amazon_fee_pct_for_row(row, amazon_fees_data, global_default_fee_pct), axis=1
    )
    df_updated['diff_euro'], df_updated['diff_pct'] = calculate_diffs(df_updated)
    df_updated['net_margin'] = calculate_net_margin(df_updated)
    return df_updated

def apply_scale_price(df: pd.DataFrame, selected_indices: List[int], scale_value: float, is_percentage: bool) -> pd.DataFrame:
    if not selected_indices: return df
    df_modified = df.copy()
    prices_loc = df_modified.iloc[selected_indices]['nostro_prezzo']
    prices = pd.to_numeric(prices_loc, errors='coerce').fillna(0)
    if is_percentage: new_prices = prices * (1 - (scale_value / 100.0))
    else: new_prices = prices - scale_value
    df_modified.iloc[selected_indices, df_modified.columns.get_loc('nostro_prezzo')] = np.maximum(0.01, new_prices).round(2)
    return df_modified

def apply_align_to_buybox(df: pd.DataFrame, selected_indices: List[int], delta_value: float, is_percentage: bool) -> pd.DataFrame:
    if not selected_indices: return df
    df_modified = df.copy()
    buybox_prices_selected_loc = df_modified.iloc[selected_indices]['buybox_price']
    buybox_prices_selected = pd.to_numeric(buybox_prices_selected_loc, errors='coerce')
    valid_buybox_mask = buybox_prices_selected.notna()
    
    # Get original indices from df_modified that correspond to the selection and valid buybox
    valid_original_indices = df_modified.iloc[selected_indices][valid_buybox_mask].index

    if valid_original_indices.empty: return df_modified
    
    buybox_prices_valid = buybox_prices_selected[valid_buybox_mask]
    
    if is_percentage: new_prices = buybox_prices_valid * (1 - (delta_value / 100.0))
    else: new_prices = buybox_prices_valid - delta_value
    
    # Use .loc with original indices for assignment
    df_modified.loc[valid_original_indices, 'nostro_prezzo'] = np.maximum(0.01, new_prices).round(2)
    return df_modified