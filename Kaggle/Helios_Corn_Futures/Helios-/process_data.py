# 1. Environment Setup & Data Loading

from IPython.display import display
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import warnings
import os

# Configuration Settings
warnings.filterwarnings('ignore')          
pd.set_option('display.max_columns', None) 
pd.set_option('display.max_rows', 100)     
plt.style.use('seaborn-v0_8-whitegrid')    

# Define file paths
BASE_PATH = '/kaggle/input/forecasting-the-future-the-helios-corn-climate-challenge/'
MAIN_FILE = 'data\corn_climate_risk_futures_daily_master.csv'
SHARE_FILE = 'data\corn_regional_market_share.csv'

# Load Data
print("Loading data...")

df = pd.read_csv(MAIN_FILE)
market_share = pd.read_csv(SHARE_FILE)
print("Data loaded successfully.")

# Display Data Overview
print("\n" + "="*50)
print(f"Main Dataset Shape: {df.shape}")
print("="*50)
display(df.head())

# Important: Identification of target rows (This will help prevent ID mismatch)
target_col = 'futures_close_ZC_1'
if target_col in df.columns:
    missing_targets = df[target_col].isnull().sum()
    print(f"\nTarget column: {target_col}")
    print(f"Rows with missing targets (to be predicted): {missing_targets}")