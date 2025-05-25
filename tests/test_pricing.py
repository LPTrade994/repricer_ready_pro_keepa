import pytest
import pandas as pd
import numpy as np
from services import pricing

def test_calculate_initial_shipping_cost(sample_amazon_df):
    """Tests initial shipping cost calculation."""
    df = sample_amazon_df.copy()
    shipping_costs = pricing.calculate_initial_shipping_cost(df, 'Sito')
    assert shipping_costs.iloc[0] == 5.14  # Italia
    assert shipping_costs.iloc[1] == 11.50 # Francia
    assert shipping_costs.iloc[2] == 5.14  # Italia
    assert shipping_costs.iloc[3] == 11.50 # Germania

def test_calculate_diffs(sample_merged_df):
    """Tests calculation of diff_euro and diff_pct."""
    df = sample_merged_df.copy()
    diff_euro, diff_pct = pricing.calculate_diffs(df)

    # Row 0: nostro_prezzo=100, buybox_price=90
    assert diff_euro.iloc[0] == -10.00  # 90 - 100
    assert diff_pct.iloc[0] == -10.00  # (90/100 - 1)*100
    
    # Row 1: nostro_prezzo=150, buybox_price=160
    assert diff_euro.iloc[1] == 10.00   # 160 - 150
    assert np.isclose(diff_pct.iloc[1], (160/150 - 1)*100)

    # Row 2: nostro_prezzo=60, buybox_price=NaN
    assert pd.isna(diff_euro.iloc[2])
    assert pd.isna(diff_pct.iloc[2])

    # Row 3: nostro_prezzo=NaN, buybox_price=80
    assert pd.isna(diff_euro.iloc[3])
    assert pd.isna(diff_pct.iloc[3])

def test_calculate_net_margin(sample_merged_df):
    """Tests net margin calculation."""
    df = sample_merged_df.copy()
    amazon_fee_pct_value = 15.0
    net_margins = pricing.calculate_net_margin(df, amazon_fee_pct_value)

    # Row 0: P=100, S=5.14, Fee=15% -> Margin = 100 - (100*0.15) - 5.14 = 100 - 15 - 5.14 = 79.86
    assert net_margins.iloc[0] == 79.86
    
    # Row 1: P=150, S=11.50, Fee=15% -> Margin = 150 - (150*0.15) - 11.50 = 150 - 22.5 - 11.50 = 116.00
    assert net_margins.iloc[1] == 116.00

    # Row 2: P=60, S=5.14, Fee=15% -> Margin = 60 - (60*0.15) - 5.14 = 60 - 9 - 5.14 = 45.86
    assert net_margins.iloc[2] == 45.86

    # Row 3: P=NaN
    assert pd.isna(net_margins.iloc[3])


def test_apply_scale_price_absolute(sample_merged_df):
    """Tests scaling price by an absolute amount."""
    df = sample_merged_df.copy()
    indices_to_scale = [0, 1] # Scale first two rows
    scaled_df = pricing.apply_scale_price(df, indices_to_scale, scale_value=10.0, is_percentage=False)
    
    assert scaled_df.loc[0, 'nostro_prezzo'] == 90.00  # 100 - 10
    assert scaled_df.loc[1, 'nostro_prezzo'] == 140.00 # 150 - 10
    assert scaled_df.loc[2, 'nostro_prezzo'] == df.loc[2, 'nostro_prezzo'] # Unchanged

    # Test minimum price
    scaled_df_min = pricing.apply_scale_price(df, [0], scale_value=1000.0, is_percentage=False)
    assert scaled_df_min.loc[0, 'nostro_prezzo'] == 0.01


def test_apply_scale_price_percentage(sample_merged_df):
    """Tests scaling price by a percentage."""
    df = sample_merged_df.copy()
    indices_to_scale = [0, 1] 
    scaled_df = pricing.apply_scale_price(df, indices_to_scale, scale_value=10.0, is_percentage=True) # -10%
    
    assert scaled_df.loc[0, 'nostro_prezzo'] == 90.00  # 100 * (1 - 0.10)
    assert scaled_df.loc[1, 'nostro_prezzo'] == 135.00 # 150 * (1 - 0.10)
    assert scaled_df.loc[2, 'nostro_prezzo'] == df.loc[2, 'nostro_prezzo'] # Unchanged

def test_apply_align_to_buybox_absolute(sample_merged_df):
    """Tests aligning price to buybox with an absolute delta."""
    df = sample_merged_df.copy()
    indices_to_align = [0, 1] # Align first two rows
    # Row 0: BB=90. Delta=5. New Price = 90 - 5 = 85
    # Row 1: BB=160. Delta=5. New Price = 160 - 5 = 155
    aligned_df = pricing.apply_align_to_buybox(df, indices_to_align, delta_value=5.0, is_percentage=False)
    
    assert aligned_df.loc[0, 'nostro_prezzo'] == 85.00
    assert aligned_df.loc[1, 'nostro_prezzo'] == 155.00
    assert aligned_df.loc[2, 'nostro_prezzo'] == df.loc[2, 'nostro_prezzo'] # Unchanged (BB is NaN)
    assert pd.isna(aligned_df.loc[3, 'nostro_prezzo']) # Unchanged (original price was NaN)

    # Test minimum price
    aligned_df_min = pricing.apply_align_to_buybox(df, [0], delta_value=100.0, is_percentage=False) # BB=90, 90-100 = -10 -> 0.01
    assert aligned_df_min.loc[0, 'nostro_prezzo'] == 0.01


def test_apply_align_to_buybox_percentage(sample_merged_df):
    """Tests aligning price to buybox with a percentage delta."""
    df = sample_merged_df.copy()
    indices_to_align = [0, 1]
    # Row 0: BB=90. Delta=10%. New Price = 90 * (1 - 0.10) = 81
    # Row 1: BB=160. Delta=10%. New Price = 160 * (1 - 0.10) = 144
    aligned_df = pricing.apply_align_to_buybox(df, indices_to_align, delta_value=10.0, is_percentage=True)
    
    assert aligned_df.loc[0, 'nostro_prezzo'] == 81.00
    assert aligned_df.loc[1, 'nostro_prezzo'] == 144.00
    assert aligned_df.loc[2, 'nostro_prezzo'] == df.loc[2, 'nostro_prezzo'] # Unchanged (BB is NaN)