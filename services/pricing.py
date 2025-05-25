import pandas as pd
import numpy as np
from typing import List, Tuple

def calculate_initial_shipping_cost(df: pd.DataFrame, sito_column_name: str = 'Sito') -> pd.Series:
    """
    Calculates initial shipping cost based on the 'Sito' column.
    5.14 if 'Sito' contains 'Italia', 11.50 otherwise.

    Args:
        df (pd.DataFrame): DataFrame containing the site information.
        sito_column_name (str): Name of the column containing site information (e.g., "Italia - Amazon.it").

    Returns:
        pd.Series: Series with shipping costs.
    """
    return pd.Series(np.where(df[sito_column_name].str.contains('Italia', case=False, na=False), 5.14, 11.50), index=df.index)


def calculate_diffs(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
    """
    Calculates diff_euro (buybox_price - nostro_prezzo) and 
    diff_pct ((buybox_price / nostro_prezzo - 1) * 100).

    Args:
        df (pd.DataFrame): DataFrame must contain 'buybox_price' and 'nostro_prezzo' columns.

    Returns:
        Tuple[pd.Series, pd.Series]: diff_euro, diff_pct
    """
    nostro_prezzo_numeric = pd.to_numeric(df['nostro_prezzo'], errors='coerce')
    buybox_price_numeric = pd.to_numeric(df['buybox_price'], errors='coerce')

    diff_euro = buybox_price_numeric - nostro_prezzo_numeric
    
    # Calculate diff_pct, handling division by zero or NaN nostro_prezzo
    diff_pct = pd.Series(index=df.index, dtype='float64')
    valid_prices_mask = (nostro_prezzo_numeric.notna()) & (nostro_prezzo_numeric != 0) & (buybox_price_numeric.notna())
    
    diff_pct.loc[valid_prices_mask] = \
        (buybox_price_numeric.loc[valid_prices_mask] / nostro_prezzo_numeric.loc[valid_prices_mask] - 1) * 100
    
    return diff_euro.round(2), diff_pct.round(2)


def calculate_net_margin(df: pd.DataFrame, amazon_fee_pct_value: float) -> pd.Series:
    """
    Calculates net_margin: nostro_prezzo - (amazon_fee_pct % of nostro_prezzo) - shipping_cost.

    Args:
        df (pd.DataFrame): DataFrame must contain 'nostro_prezzo', 'shipping_cost'.
                           'amazon_fee_pct_col' can be used if present, otherwise uses amazon_fee_pct_value.
        amazon_fee_pct_value (float): Amazon fee percentage (e.g., 15 for 15%).

    Returns:
        pd.Series: net_margin
    """
    nostro_prezzo_numeric = pd.to_numeric(df['nostro_prezzo'], errors='coerce')
    shipping_cost_numeric = pd.to_numeric(df['shipping_cost'], errors='coerce')
    
    # Use per-row fee if available, else global
    if 'amazon_fee_pct_col' in df.columns:
        fee_pct_series = pd.to_numeric(df['amazon_fee_pct_col'], errors='coerce') / 100.0
    else:
        fee_pct_series = amazon_fee_pct_value / 100.0

    amazon_fee_amount = nostro_prezzo_numeric * fee_pct_series
    net_margin = nostro_prezzo_numeric - amazon_fee_amount - shipping_cost_numeric
    return net_margin.round(2)


def update_all_calculated_columns(df: pd.DataFrame, amazon_fee_pct_value: float) -> pd.DataFrame:
    """
    Updates all calculated columns: diff_euro, diff_pct, net_margin.
    Assumes 'nostro_prezzo', 'buybox_price', 'shipping_cost', 'amazon_fee_pct_col' are present and correct.

    Args:
        df (pd.DataFrame): The DataFrame to update.
        amazon_fee_pct_value (float): Current global Amazon fee percentage.

    Returns:
        pd.DataFrame: DataFrame with updated calculated columns.
    """
    df_updated = df.copy()
    
    # Ensure essential columns are numeric for calculations
    for col in ['nostro_prezzo', 'buybox_price', 'shipping_cost', 'amazon_fee_pct_col']:
        if col in df_updated.columns:
            df_updated[col] = pd.to_numeric(df_updated[col], errors='coerce')

    if 'amazon_fee_pct_col' not in df_updated.columns: # If it wasn't there (e.g. first run)
         df_updated['amazon_fee_pct_col'] = amazon_fee_pct_value
    else: # Ensure it uses the global value passed, unless logic changes later for per-row fees
         df_updated['amazon_fee_pct_col'] = amazon_fee_pct_value


    df_updated['diff_euro'], df_updated['diff_pct'] = calculate_diffs(df_updated)
    df_updated['net_margin'] = calculate_net_margin(df_updated, amazon_fee_pct_value)
    return df_updated


def apply_scale_price(df: pd.DataFrame, selected_indices: List[int], 
                      scale_value: float, is_percentage: bool) -> pd.DataFrame:
    """
    Applies price scaling (-X € or -Y %) to 'nostro_prezzo' for selected rows.

    Args:
        df (pd.DataFrame): DataFrame to modify.
        selected_indices (List[int]): List of row indices to apply scaling.
        scale_value (float): The value to scale by (absolute or percentage).
        is_percentage (bool): True if scale_value is a percentage, False for absolute euro value.

    Returns:
        pd.DataFrame: Modified DataFrame.
    """
    if not selected_indices:
        return df

    df_modified = df.copy()
    prices = pd.to_numeric(df_modified.loc[selected_indices, 'nostro_prezzo'], errors='coerce').fillna(0)

    if is_percentage:
        new_prices = prices * (1 - (scale_value / 100.0))
    else:
        new_prices = prices - scale_value
    
    # Ensure price doesn't go below a minimum (e.g., 0.01)
    df_modified.loc[selected_indices, 'nostro_prezzo'] = np.maximum(0.01, new_prices).round(2)
    return df_modified


def apply_align_to_buybox(df: pd.DataFrame, selected_indices: List[int], 
                          delta_value: float, is_percentage: bool) -> pd.DataFrame:
    """
    Aligns 'nostro_prezzo' to 'buybox_price' - Δ for selected rows.
    Δ can be an absolute euro value or a percentage of buybox_price.

    Args:
        df (pd.DataFrame): DataFrame to modify.
        selected_indices (List[int]): List of row indices to apply alignment.
        delta_value (float): The delta value.
        is_percentage (bool): True if delta_value is a percentage, False for absolute euro value.

    Returns:
        pd.DataFrame: Modified DataFrame.
    """
    if not selected_indices:
        return df

    df_modified = df.copy()
    
    buybox_prices_selected = pd.to_numeric(df_modified.loc[selected_indices, 'buybox_price'], errors='coerce')
    
    # Create a mask for rows within selection that have a valid buybox_price
    valid_buybox_mask = buybox_prices_selected.notna()
    valid_indices = buybox_prices_selected[valid_buybox_mask].index

    if valid_indices.empty: # No valid buybox prices in selection
        return df_modified

    buybox_prices_valid = buybox_prices_selected[valid_buybox_mask]

    if is_percentage:
        # Delta is a percentage of buybox_price
        new_prices = buybox_prices_valid * (1 - (delta_value / 100.0))
    else:
        # Delta is an absolute euro value
        new_prices = buybox_prices_valid - delta_value
    
    # Ensure price doesn't go below a minimum (e.g., 0.01)
    df_modified.loc[valid_indices, 'nostro_prezzo'] = np.maximum(0.01, new_prices).round(2)
    return df_modified