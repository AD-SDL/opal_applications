"""
Opentrons OT-2/Flex Protocol for Automated Media Preparation

This protocol reads CSV files and performs automated liquid transfers for media optimization.
Upload this file directly to the Opentrons App along with required CSV files.

Required CSV files (upload as runtime parameters or place in protocol directory):
- stock_concentrations.csv
- standard_recipe_concentrations.csv
- target_concentrations.csv
- 24-well_stock_plate_high.csv
- 24-well_stock_plate_low.csv
- 24-well_stock_plate_fresh.csv
"""

from opentrons import protocol_api
import pandas as pd
import numpy as np

metadata = {
    'protocolName': 'Automated Media Preparation',
    'author': 'Converted from Biomek',
    'description': 'Media optimization with multiple component transfers from CSV inputs',
    'apiLevel': '2.13'
}

# ============================================================================
# CONFIGURATION
# ============================================================================

CONFIG = {
    'well_volume': 1500,            # Total volume in destination well (µL)
    'min_transfer_volume': 1.0,     # Minimum transfer volume (µL)
    'culture_factor': 100,          # Dilution factor for culture
    'dead_volume': 100,             # Dead volume in source wells (µL)
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def find_volumes_single(stock_high, stock_low, target_conc, well_volume, min_volume, culture_ratio):
    """
    Calculate transfer volumes for a single component.
    
    Returns:
        volume: Transfer volume in µL
        level: 'high' or 'low' stock concentration to use
    """
    if target_conc == 0:
        return 0, None
    
    # Try high concentration first
    if stock_high > 0:
        vol_high = (target_conc * well_volume) / stock_high
        if vol_high >= min_volume and vol_high <= well_volume / culture_ratio:
            return vol_high, 'high'
    
    # Try low concentration
    if stock_low > 0:
        vol_low = (target_conc * well_volume) / stock_low
        if vol_low >= min_volume and vol_low <= well_volume / culture_ratio:
            return vol_low, 'low'
    
    # If neither works, use the closer one
    if stock_high > 0:
        return (target_conc * well_volume) / stock_high, 'high'
    elif stock_low > 0:
        return (target_conc * well_volume) / stock_low, 'low'
    
    return 0, None

def calculate_transfer_volumes(df_stock, df_target_conc, well_volume, min_volume, culture_ratio):
    """Calculate all transfer volumes and concentration levels."""
    
    df_volumes = pd.DataFrame(index=df_target_conc.index, columns=df_stock.index)
    df_conc_level = pd.DataFrame(index=df_target_conc.index, columns=df_stock.index)
    
    for well in df_target_conc.index:
        for comp in df_stock.index:
            if comp == 'Kan':
                # Kanamycin uses fixed concentration
                df_volumes.at[well, comp] = (df_target_conc.at[well, comp] * well_volume) / df_stock.at[comp, 'High Concentration']
                df_conc_level.at[well, comp] = 'high'
            else:
                target = df_target_conc.at[well, comp]
                stock_high = df_stock.at[comp, 'High Concentration']
                stock_low = df_stock.at[comp, 'Low Concentration']
                
                vol, level = find_volumes_single(stock_high, stock_low, target, well_volume, min_volume, culture_ratio)
                df_volumes.at[well, comp] = vol
                df_conc_level.at[well, comp] = level
    
    # Convert to float
    df_volumes = df_volumes.astype(float)
    
    # Calculate water to fill to final volume
    total_other = df_volumes.sum(axis=1)
    culture_vol = well_volume / culture_ratio
    df_volumes['Water'] = well_volume - total_other - culture_vol
    df_volumes['Culture'] = culture_vol
    
    return df_volumes, df_conc_level

def load_csv_inputs(protocol):
    """Load all required CSV files."""
    
    protocol.comment("Loading CSV data files...")
    
    # In a real Opentrons run, these would be loaded from the protocol directory
    # For simulation/testing, you'll need to ensure these files are accessible
    
    try:
        df_stock = pd.read_csv('../csv_inputs/stock_concentrations.csv').set_index("Component")
        df_standard = pd.read_csv('../csv_inputs/standard_recipe_concentrations.csv').set_index("Component")
        df_target = pd.read_csv('../csv_inputs/target_concentrations.csv', index_col=0)
        df_stock_high = pd.read_csv('../csv_inputs/24-well_stock_plate_high.csv').set_index("Well")
        df_stock_low = pd.read_csv('../csv_inputs/24-well_stock_plate_low.csv').set_index("Well")
        df_stock_fresh = pd.read_csv('../csv_inputs/24-well_stock_plate_fresh.csv').set_index("Well")
        
        # Format stock concentrations
        if 'Kan' in df_stock.index:
            df_stock.loc['Kan'] = [300., 300., 1.]
        df_stock["High Concentration"] = df_stock["High Concentration"].astype(float)
        df_stock["Low Concentration"] = df_stock["Low Concentration"].astype(float)
        
        # Add fixed components from standard recipe to target concentrations
        for column in df_target.columns:
                df_standard.drop(column, axis=0, inplace=True)

        comp_fixed = list(df_standard.index)
        for comp in comp_fixed:
            df_target[comp] = df_standard.at[comp, 'Concentration[mM]']
        
        # Reorder columns to match stock
        df_target = df_target[df_stock.index]
        
        return df_stock, df_target, df_stock_high, df_stock_low, df_stock_fresh
        
    except Exception as e:
        protocol.comment(f"ERROR loading CSV files: {str(e)}")
        protocol.comment("Please ensure all CSV files are in the protocol directory")
        raise

# ============================================================================
# MAIN PROTOCOL
# ============================================================================

def run(protocol: protocol_api.ProtocolContext):
    
    protocol.comment("="*50)
    protocol.comment("Automated Media Preparation Protocol")
    protocol.comment("="*50)
    
    # ------------------------------------------------------------------------
    # Load data
    # ------------------------------------------------------------------------
    
    df_stock, df_target_conc, df_stock_high, df_stock_low, df_stock_fresh = load_csv_inputs(protocol)
    
    protocol.comment(f"Loaded data for {len(df_target_conc)} destination wells")
    protocol.comment(f"Components: {len(df_stock)} total")
    
    # ------------------------------------------------------------------------
    # Calculate volumes
    # ------------------------------------------------------------------------
    
    protocol.comment("Calculating transfer volumes...")
    
    df_volumes, df_conc_level = calculate_transfer_volumes(
        df_stock=df_stock,
        df_target_conc=df_target_conc,
        well_volume=CONFIG['well_volume'],
        min_volume=CONFIG['min_transfer_volume'],
        culture_ratio=CONFIG['culture_factor']
    )
    
    # Validate volumes
    total_vols = df_volumes.sum(axis=1)
    if not all(abs(total_vols - CONFIG['well_volume']) < 0.01):
        protocol.comment("WARNING: Volume calculations don't sum to target!")
    
    # ------------------------------------------------------------------------
    # Setup labware
    # ------------------------------------------------------------------------
    
    protocol.comment("Setting up labware...")
    
    # Tips
    tiprack_20_1 = protocol.load_labware('opentrons_96_tiprack_20ul', 1)
    tiprack_20_2 = protocol.load_labware('opentrons_96_tiprack_20ul', 2)
    tiprack_300_1 = protocol.load_labware('opentrons_96_tiprack_300ul', 3)
    tiprack_300_2 = protocol.load_labware('opentrons_96_tiprack_300ul', 4)
    
    # Plates
    dest_plate = protocol.load_labware('nest_24_wellplate_10.4ml', 5, 'Destination Plate')
    stock_high = protocol.load_labware('nest_24_wellplate_10.4ml', 6, 'Stock High Conc')
    stock_low = protocol.load_labware('nest_24_wellplate_10.4ml', 7, 'Stock Low Conc')
    stock_fresh = protocol.load_labware('nest_24_wellplate_10.4ml', 8, 'Stock Fresh')
    reservoir = protocol.load_labware('nest_12_reservoir_15ml', 9, 'Water Reservoir')
    
    # Pipettes
    p20 = protocol.load_instrument('p20_single_gen2', 'right', 
                                    tip_racks=[tiprack_20_1, tiprack_20_2])
    p300 = protocol.load_instrument('p300_single_gen2', 'left', 
                                     tip_racks=[tiprack_300_1, tiprack_300_2])
    
    # Set flow rates for accuracy
    p20.flow_rate.aspirate = 7.56
    p20.flow_rate.dispense = 7.56
    p300.flow_rate.aspirate = 92.86
    p300.flow_rate.dispense = 92.86
    
    # Map plate names to labware
    plate_map = {
        'stock_high': stock_high,
        'stock_low': stock_low,
        'stock_fresh': stock_fresh
    }
    
    # ------------------------------------------------------------------------
    # Helper function for transfers
    # ------------------------------------------------------------------------
    
    def smart_transfer(volume, source, dest, pip_choice='auto', mix_after=None):
        """Perform a transfer with automatic pipette selection."""
        if volume < 1.0:
            return  # Skip transfers below minimum
        
        if pip_choice == 'auto':
            pipette = p20 if volume < 20 else p300
        elif pip_choice == 'p20':
            pipette = p20
        else:
            pipette = p300
        
        # Check if volume is within pipette range
        if volume > pipette.max_volume:
            # Split into multiple transfers
            num_transfers = int(np.ceil(volume / pipette.max_volume))
            vol_per_transfer = volume / num_transfers
            for _ in range(num_transfers):
                pipette.transfer(vol_per_transfer, source, dest, new_tip='always')
        else:
            if mix_after:
                pipette.transfer(volume, source, dest, new_tip='always', 
                               mix_after=mix_after)
            else:
                pipette.transfer(volume, source, dest, new_tip='always')
    
    # ------------------------------------------------------------------------
    # Calculate and report resource requirements
    # ------------------------------------------------------------------------
    
    total_water = df_volumes['Water'].sum()
    total_culture = df_volumes['Culture'].sum()
    
    protocol.comment(f"\nResource requirements:")
    protocol.comment(f"  Water: {total_water:.0f} µL")
    protocol.comment(f"  Culture: {total_culture:.0f} µL")
    
    # Count transfers by pipette
    water_20 = len([v for v in df_volumes['Water'] if 0 < v < 20])
    water_300 = len([v for v in df_volumes['Water'] if v >= 20])
    protocol.comment(f"  Water transfers: {water_20} (p20) + {water_300} (p300)")
    
    # ------------------------------------------------------------------------
    # WATER TRANSFERS
    # ------------------------------------------------------------------------
    
    protocol.comment("\n" + "="*50)
    protocol.comment("STEP 1: Transferring Water")
    protocol.comment("="*50)
    
    water_source = reservoir['A1']
    transfer_count = 0
    
    for well_id in df_volumes.index:
        volume = df_volumes.at[well_id, 'Water']
        if volume > 0:
            smart_transfer(volume, water_source, dest_plate[well_id])
            transfer_count += 1
            if transfer_count % 10 == 0:
                protocol.comment(f"  Completed {transfer_count} water transfers")
    
    protocol.comment(f"Water transfers complete: {transfer_count} total")
    
    # ------------------------------------------------------------------------
    # KANAMYCIN TRANSFERS
    # ------------------------------------------------------------------------
    
    protocol.comment("\n" + "="*50)
    protocol.comment("STEP 2: Transferring Kanamycin")
    protocol.comment("="*50)
    
    # Find kan source well
    kan_wells = df_stock_high[df_stock_high["Component"] == 'Kan'].index
    if len(kan_wells) > 0:
        kan_source = stock_high[kan_wells[0]]
        transfer_count = 0
        
        for well_id in df_volumes.index:
            volume = df_volumes.at[well_id, 'Kan']
            if volume > 0:
                smart_transfer(volume, kan_source, dest_plate[well_id])
                transfer_count += 1
        
        protocol.comment(f"Kanamycin transfers complete: {transfer_count} total")
    else:
        protocol.comment("No Kanamycin source found, skipping")
    
    # ------------------------------------------------------------------------
    # COMPONENT TRANSFERS
    # ------------------------------------------------------------------------
    
    protocol.comment("\n" + "="*50)
    protocol.comment("STEP 3: Transferring Components")
    protocol.comment("="*50)
    
    components = [c for c in df_volumes.columns if c not in ['Water', 'Kan', 'Culture']]
    transfer_count = 0
    
    for comp in components:
        comp_transfers = 0
        
        for well_id in df_volumes.index:
            volume = df_volumes.at[well_id, comp]
            if volume > 0:
                conc_level = df_conc_level.at[well_id, comp]
                
                # Determine source
                if comp == 'FeSO4':
                    source_plate = plate_map['stock_fresh']
                    source_well = "B1" if conc_level == 'low' else "C1"
                else:
                    if conc_level == 'high':
                        source_plate = plate_map['stock_high']
                        df_source = df_stock_high
                    else:
                        source_plate = plate_map['stock_low']
                        df_source = df_stock_low
                    
                    # Find source well
                    source_wells = df_source[df_source["Component"] == comp].index
                    if len(source_wells) > 0:
                        source_well = source_wells[0]
                    else:
                        protocol.comment(f"WARNING: No source found for {comp}")
                        continue
                
                smart_transfer(volume, source_plate[source_well], dest_plate[well_id])
                comp_transfers += 1
                transfer_count += 1
        
        if comp_transfers > 0:
            protocol.comment(f"  {comp}: {comp_transfers} transfers")
    
    protocol.comment(f"Component transfers complete: {transfer_count} total")
    
    # ------------------------------------------------------------------------
    # CULTURE TRANSFERS
    # ------------------------------------------------------------------------
    
    protocol.comment("\n" + "="*50)
    protocol.comment("STEP 4: Transferring Culture")
    protocol.comment("="*50)
    protocol.comment("PAUSE: Prepare fresh culture plate if needed")
    
    protocol.pause("Replace plates with fresh culture if needed, then resume")
    
    # Find culture source well
    culture_wells = df_stock_fresh[df_stock_fresh["Component"] == 'Culture'].index
    if len(culture_wells) > 0:
        culture_source = stock_fresh[culture_wells[0]]
        culture_volume = df_volumes['Culture'].iloc[0]
        transfer_count = 0
        
        for well_id in df_volumes.index:
            # Transfer with mixing
            smart_transfer(culture_volume, culture_source, dest_plate[well_id],
                         mix_after=(3, 10))
            transfer_count += 1
            if transfer_count % 10 == 0:
                protocol.comment(f"  Completed {transfer_count} culture transfers")
        
        protocol.comment(f"Culture transfers complete: {transfer_count} total")
    else:
        protocol.comment("ERROR: No culture source found!")
    
    # ------------------------------------------------------------------------
    # COMPLETION
    # ------------------------------------------------------------------------
    
    protocol.comment("\n" + "="*50)
    protocol.comment("PROTOCOL COMPLETE")
    protocol.comment("="*50)
    protocol.comment(f"Total wells prepared: {len(df_volumes)}")
    protocol.comment("Remove destination plate and proceed with incubation")