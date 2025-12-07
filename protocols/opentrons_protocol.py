"""
Opentrons OT-2/Flex Protocol for Automated Media Preparation
This is a first draft translating the Biomek protocol to Opentrons API using Claude.
It has not been tested and will need fixes. 

This protocol generates files for media optimization and creates an Opentrons protocol
to automate liquid transfers using the OT-2 or Flex robot.

Inputs:
- standard_recipe_concentrations.csv
- stock_concentrations.csv
- target_concentrations.csv
- 24-well stock plate layout files

Outputs:
- dest_volumes.csv
- media_descriptions.csv
- opentrons_protocol.py (executable protocol file)
"""

import os
import sys
sys.path.append('../')

import pandas as pd
import numpy as np
from textwrap import dedent

from core import find_volumes, find_volumes_bulk

# ============================================================================
# USER PARAMETERS
# ============================================================================

CYCLE = 6

user_params = {
    'stock_conc_file': '../data/flaviolin/stock_concentrations.csv',
    'standard_media_file': '../data/flaviolin/standard_recipe_concentrations.csv',
    'stock_plate_high_file': '../data/flaviolin/24-well_stock_plate_high.csv',
    'stock_plate_low_file': '../data/flaviolin/24-well_stock_plate_low.csv',
    'stock_plate_fresh_file': '../data/flaviolin/24-well_stock_plate_fresh.csv',
    'target_conc_file': f'../data/flaviolin/DBTL{CYCLE}/target_concentrations.csv',
    'output_path': f'../data/flaviolin/DBTL{CYCLE}',
    'well_volume': 1500,            # Total volume in destination well (µL)
    'min_transfer_volume': 1.0,     # Minimum transfer volume for Opentrons (µL)
    'culture_factor': 100,          # Dilution factor for culture
    'pipette_left': 'p300_single_gen2',   # Left mount pipette
    'pipette_right': 'p20_single_gen2',   # Right mount pipette
}

# Opentrons pipette specifications
pipette_specs = {
    'p20_single_gen2': {'min': 1, 'max': 20},
    'p300_single_gen2': {'min': 20, 'max': 300},
    'p1000_single_gen2': {'min': 100, 'max': 1000},
    'flex_1channel_50': {'min': 1, 'max': 50},
    'flex_1channel_1000': {'min': 5, 'max': 1000},
}

# ============================================================================
# LOAD DATA
# ============================================================================

print("Loading data files...")

# Load standard media recipe
df_stand = pd.read_csv(user_params['standard_media_file']).set_index("Component")

# Load stock concentrations and stock plate layouts
df_stock = pd.read_csv(user_params['stock_conc_file']).set_index("Component")
df_stock_plate_high = pd.read_csv(user_params['stock_plate_high_file'])
df_stock_plate_low = pd.read_csv(user_params['stock_plate_low_file'])
df_stock_plate_fresh = pd.read_csv(user_params['stock_plate_fresh_file'])

# Reformat values
df_stock.loc['Kan'] = [300., 300., 1.]
df_stock["High Concentration[mM]"] = df_stock["High Concentration[mM]"].astype(float)
df_stock["Low Concentration[mM]"] = df_stock["Low Concentration[mM]"].astype(float)

# ============================================================================
# READ TARGET CONCENTRATIONS
# ============================================================================

df_target_conc = pd.read_csv(user_params['target_conc_file'], index_col=0)

# Add fixed components from standard recipe
comp_fixed = list(df_stand.drop(df_target_conc.columns).index)
print('Fixed components:')
for comp in comp_fixed:
    df_target_conc[comp] = df_stand.at[comp, 'Concentration[mM]']
    print(f'  {comp}')

# Reorder columns to match stock dataframe
columns = df_stock.index
df_target_conc = df_target_conc[columns]

# Save media descriptions
final_conc_file = f"{user_params['output_path']}/media_descriptions.csv"
df_target_conc.drop(columns='Kan').to_csv(final_conc_file)

# ============================================================================
# CALCULATE TRANSFER VOLUMES
# ============================================================================

print("\nCalculating transfer volumes...")

df_volumes, df_conc_level = find_volumes_bulk(
    df_stock=df_stock, 
    df_target_conc=df_target_conc,
    well_volume=user_params['well_volume'],
    min_tip_volume=user_params['min_transfer_volume'],
    culture_ratio=user_params['culture_factor']
)

# Add culture volumes
df_volumes['Culture'] = user_params['well_volume'] / user_params['culture_factor']

# Verify total volumes
EPS = 0.000001
assert (np.sum(df_volumes.values, axis=1) - user_params['well_volume'] <= EPS).all(), \
    'Sum of all volumes is not equal to total well volume!'

# Save volumes
volumes_file = f"{user_params['output_path']}/dest_volumes.csv"
df_volumes.to_csv(volumes_file)

print(f"Saved destination volumes to {volumes_file}")

# ============================================================================
# PREPARE SOURCE PLATE LAYOUTS
# ============================================================================

well_volume = 9000  # including dead volume
dead_volume = 100

# Process high concentration plate
df_stock_plate_high['Volume [uL]'] = None
for i in range(len(df_stock_plate_high)-2):
    comp = df_stock_plate_high.iloc[i]['Component']
    stock_level = 'high'
    tot_vol_comp = np.sum(
        df_volumes[df_conc_level[comp]==stock_level][comp].values
    )
    df_stock_plate_high.loc[i, 'Volume [uL]'] = np.round(tot_vol_comp) + dead_volume

# Assign well names
well_rows = 'ABCD'
well_columns = '123456'
num_source_wells = len(df_stock_plate_high) 
well_names = [f'{row}{column}' for column in well_columns for row in well_rows]
well_names = well_names[:num_source_wells]
df_stock_plate_high['Well'] = well_names
df_stock_plate_high = df_stock_plate_high.set_index("Well")

# Process low concentration plate
df_stock_plate_low['Volume [uL]'] = None
for i in range(len(df_stock_plate_low)):
    comp = df_stock_plate_low.iloc[i]['Component']
    stock_level = 'low'
    tot_vol_comp = np.sum(
        df_volumes[df_conc_level[comp]==stock_level][comp].values
    )
    df_stock_plate_low.iloc[i, df_stock_plate_low.columns.get_loc('Volume [uL]')] = \
        np.round(tot_vol_comp) + dead_volume

df_stock_plate_low = df_stock_plate_low.set_index("Well")

# Process fresh components plate
df_stock_plate_fresh['Volume [uL]'] = None
comp = 'FeSO4'
for i, stock_level in enumerate(list(['low', 'high'])):
    tot_vol_comp = np.sum(
        df_volumes[df_conc_level[comp]==stock_level][comp].values
    )
    df_stock_plate_fresh.loc[i+1, 'Volume [uL]'] = np.round(tot_vol_comp) + dead_volume

# Culture
tot_vol_culture = np.sum(df_volumes['Culture'].values)
df_stock_plate_fresh.loc[0, 'Volume [uL]'] = np.round(tot_vol_culture) + dead_volume
df_stock_plate_fresh = df_stock_plate_fresh.set_index("Well")

# Save stock plate instructions
stock_plate_file = f"{user_params['output_path']}/24-well_stock_plate_high.csv"
df_stock_plate_high.to_csv(stock_plate_file)
stock_plate_file = f"{user_params['output_path']}/24-well_stock_plate_low.csv"
df_stock_plate_low.to_csv(stock_plate_file)
stock_plate_file = f"{user_params['output_path']}/24-well_stock_plate_fresh.csv"
df_stock_plate_fresh.to_csv(stock_plate_file)

# ============================================================================
# GENERATE OPENTRONS PROTOCOL
# ============================================================================

print("\nGenerating Opentrons protocol...")

# Create transfer lists for protocol generation
transfers = {
    'water': [],
    'kan': [],
    'components': [],
    'culture': []
}

# Water transfers
for dest_well in df_volumes.index:
    vol = df_volumes.at[dest_well, 'Water']
    if vol > 0:
        transfers['water'].append({
            'source': 'A1',  # Reservoir
            'dest': dest_well,
            'volume': vol
        })

# Kan transfers
for dest_well in df_volumes.index:
    vol = df_volumes.at[dest_well, 'Kan']
    if vol > 0:
        source_well = df_stock_plate_high[
            df_stock_plate_high["Component"]=='Kan'
        ].index[0]
        transfers['kan'].append({
            'source': source_well,
            'source_plate': 'stock_high',
            'dest': dest_well,
            'volume': vol
        })

# Component transfers
components = list(df_volumes.columns.drop(['Kan', 'Water', 'Culture']))
for comp in components:
    for dest_well in df_volumes.index:
        vol = df_volumes.at[dest_well, comp]
        if vol > 0:
            conc_level = df_conc_level.at[dest_well, comp]
            
            if comp == 'FeSO4':
                source_plate = 'stock_fresh'
                source_well = "B1" if conc_level == 'low' else "C1"
            else:
                source_plate = 'stock_high' if conc_level == 'high' else 'stock_low'
                df_stock_plate = df_stock_plate_high if conc_level == 'high' else df_stock_plate_low
                source_wells = df_stock_plate[df_stock_plate["Component"]==comp].index
                source_well = source_wells[0]
            
            transfers['components'].append({
                'component': comp,
                'source': source_well,
                'source_plate': source_plate,
                'dest': dest_well,
                'volume': vol
            })

# Culture transfers
vol = df_volumes['Culture'][0]
for dest_well in df_volumes.index:
    source_well = df_stock_plate_fresh[
        df_stock_plate_fresh["Component"]=='Culture'
    ].index[0]
    transfers['culture'].append({
        'source': source_well,
        'source_plate': 'stock_fresh',
        'dest': dest_well,
        'volume': vol
    })

# Generate protocol file
protocol_content = f'''from opentrons import protocol_api

metadata = {{
    'protocolName': 'Automated Media Preparation - DBTL Cycle {CYCLE}',
    'author': 'Generated from Biomek conversion script',
    'description': 'Media optimization protocol with multiple component transfers',
    'apiLevel': '2.13'
}}

def run(protocol: protocol_api.ProtocolContext):
    
    # ============================================================================
    # LABWARE
    # ============================================================================
    
    # Tips
    tiprack_20 = protocol.load_labware('opentrons_96_tiprack_20ul', 1)
    tiprack_300_1 = protocol.load_labware('opentrons_96_tiprack_300ul', 2)
    tiprack_300_2 = protocol.load_labware('opentrons_96_tiprack_300ul', 3)
    
    # Plates
    dest_plate = protocol.load_labware('nest_24_wellplate_1500ul', 4, 'Destination Plate')
    stock_high = protocol.load_labware('nest_24_wellplate_1500ul', 5, 'Stock High Conc')
    stock_low = protocol.load_labware('nest_24_wellplate_1500ul', 6, 'Stock Low Conc')
    stock_fresh = protocol.load_labware('nest_24_wellplate_1500ul', 7, 'Stock Fresh')
    reservoir = protocol.load_labware('nest_12_reservoir_15ml', 8, 'Water Reservoir')
    
    # Pipettes
    p20 = protocol.load_instrument('{user_params['pipette_right']}', 'right', tip_racks=[tiprack_20])
    p300 = protocol.load_instrument('{user_params['pipette_left']}', 'left', tip_racks=[tiprack_300_1, tiprack_300_2])
    
    # ============================================================================
    # PROTOCOL
    # ============================================================================
    
    protocol.comment("Starting media preparation protocol")
    
    # Water transfers
    protocol.comment("\\n=== Transferring Water ===")
    water_source = reservoir['A1']
'''

# Add water transfers
for t in transfers['water']:
    vol = t['volume']
    pipette = 'p20' if vol < 20 else 'p300'
    protocol_content += f"    {pipette}.transfer({vol:.1f}, water_source, dest_plate['{t['dest']}'], new_tip='always')\n"

# Add Kan transfers
protocol_content += "\n    # Kanamycin transfers\n"
protocol_content += "    protocol.comment(\"\\n=== Transferring Kanamycin ===\")\n"
for t in transfers['kan']:
    vol = t['volume']
    pipette = 'p20' if vol < 20 else 'p300'
    protocol_content += f"    {pipette}.transfer({vol:.1f}, stock_high['{t['source']}'], dest_plate['{t['dest']}'], new_tip='always')\n"

# Add component transfers
protocol_content += "\n    # Component transfers\n"
protocol_content += "    protocol.comment(\"\\n=== Transferring Components ===\")\n"
for t in transfers['components']:
    vol = t['volume']
    pipette = 'p20' if vol < 20 else 'p300'
    source_plate_var = t['source_plate'].replace('stock_', 'stock_')
    protocol_content += f"    {pipette}.transfer({vol:.1f}, {source_plate_var}['{t['source']}'], dest_plate['{t['dest']}'], new_tip='always')\n"

# Add culture transfers
protocol_content += "\n    # Culture transfers\n"
protocol_content += "    protocol.comment(\"\\n=== Transferring Culture ===\")\n"
protocol_content += "    protocol.pause('Replace stock plates with fresh culture plate if needed')\n"
for t in transfers['culture']:
    protocol_content += f"    p20.transfer({t['volume']:.1f}, stock_fresh['{t['source']}'], dest_plate['{t['dest']}'], mix_after=(3, 10), new_tip='always')\n"

protocol_content += "\n    protocol.comment(\"\\n=== Protocol Complete ===\")\n"

# Save protocol file
protocol_file = f"{user_params['output_path']}/opentrons_protocol.py"
with open(protocol_file, 'w') as f:
    f.write(protocol_content)

print(f"Saved Opentrons protocol to {protocol_file}")

# ============================================================================
# CALCULATE RESOURCE REQUIREMENTS
# ============================================================================

print("\n" + "="*70)
print("RESOURCE REQUIREMENTS")
print("="*70)

num_water_20 = len([t for t in transfers['water'] if t['volume'] < 20])
num_water_300 = len([t for t in transfers['water'] if t['volume'] >= 20])
num_kan_20 = len([t for t in transfers['kan'] if t['volume'] < 20])
num_kan_300 = len([t for t in transfers['kan'] if t['volume'] >= 20])
num_comp_20 = len([t for t in transfers['components'] if t['volume'] < 20])
num_comp_300 = len([t for t in transfers['components'] if t['volume'] >= 20])
num_culture = len(transfers['culture'])

total_20 = num_water_20 + num_kan_20 + num_comp_20 + num_culture
total_300 = num_water_300 + num_kan_300 + num_comp_300

print(f"\nTransfer counts:")
print(f"  Water (p20): {num_water_20}")
print(f"  Water (p300): {num_water_300}")
print(f"  Kanamycin (p20): {num_kan_20}")
print(f"  Kanamycin (p300): {num_kan_300}")
print(f"  Components (p20): {num_comp_20}")
print(f"  Components (p300): {num_comp_300}")
print(f"  Culture (p20): {num_culture}")
print(f"\nTotal transfers: {total_20 + total_300}")

print(f"\nTip requirements:")
print(f"  20µL tips: {total_20} tips ({np.ceil(total_20/96):.0f} box(es))")
print(f"  300µL tips: {total_300} tips ({np.ceil(total_300/96):.0f} box(es))")

print(f"\nTotal water needed: {np.sum(df_volumes['Water'].values):.0f} µL")
print(f"Total culture needed: {tot_vol_culture:.0f} µL")

print("\n" + "="*70)
print("Protocol generation complete!")
print("="*70)
print(f"\nNext steps:")
print(f"1. Review the protocol file: {protocol_file}")
print(f"2. Load the protocol in the Opentrons App")
print(f"3. Prepare labware according to the stock plate CSV files")
print(f"4. Run the protocol")