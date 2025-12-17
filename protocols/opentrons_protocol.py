from opentrons import protocol_api

# metadata
# This protocol will cherrypick sample from any well in source plate
# and transfer to any well in the destination plate
# Source, destination and volume info are provided in csv file
# Note that line 87 must be changed to trash=True before starting real experiment
metadata = {
    "protocolName": "Cherrypicking on OT-2",
    "author": "gbabnigg@anl.gov",
    "description": "Implementation of Romero protocol on the OT-2",
}

# requirements
requirements = {"robotType": "Flex", "apiLevel": "2.20"}

def add_parameters(parameters):
# the variable name must match the protocol.params.attribute (below)
    parameters.add_csv_file(
        variable_name="cherrypicking_wells",
        display_name="Cherrypicking wells",
        description=(
            "Table:"
            " source_slot, source_well,"
            " destination_slot, destination_well,"
            " volume"
        )
    )
    
# protocol run function
def run(protocol: protocol_api.ProtocolContext):
    import csv
    # well_data = protocol.params.cherrypicking_wells.parse_as_csv()
    well_data = []
    # well_data = protocol.params.cherrypicking_wells.parse_as_csv()
    with open("../csv_outputs/OTFlex_test.csv", mode='r', newline='', encoding='utf-8') as csvfile:
        # Use csv.reader to parse the file
        csv_reader = csv.reader(csvfile)
        for row in csv_reader:
            well_data.append(row)
     
    source_slots = [row[0] for row in well_data][1::] # skip first row (header) and start at index 1
    unique_source_slots = list(set(source_slots)) # unique set ['1'] -> ['1', '2']
    
    destination_slots = [row[2] for row in well_data][1::]
    unique_destination_slots = list(set(destination_slots))
    # load tip rack in deck slot A2
    tiprackB2 = protocol.load_labware(
        load_name="opentrons_flex_96_tiprack_20ul", location="B2"
    )
    tiprackB3 = protocol.load_labware(
        load_name="opentrons_flex_96_tiprack_20ul", location="B3"
    )

    tiprackC1 = protocol.load_labware(
        load_name="opentrons_flex_96_tiprack_200ul", location="C1"
    )
    tiprackC2 = protocol.load_labware(
        load_name="opentrons_flex_96_tiprack_200ul", location="C2"
    )
    tiprackC3 = protocol.load_labware(
        load_name="opentrons_flex_96_tiprack_200ul", location="C3"
    )
    
    # attach pipette to left mount
    pipette = protocol.load_instrument(
        instrument_name="flex_1channel_50",
        mount="left",
        tip_racks=[tiprackB2, tiprackB3]
    )
    pipette2 = protocol.load_instrument(
        instrument_name="flex_1channel_1000",
        mount="right",
        tip_racks=[tiprackC1, tiprackC2, tiprackC3]
    )
    # # load trash bin
    # trash = protocol.load_trash_bin("Trash") # OT-2

    # load destination plates based on CSV data
    for slot in unique_destination_slots:
        protocol.load_labware(
        load_name="opentrons_96_wellplate_200ul_pcr_full_skirt",
        location=slot
        )

    # load source plates based on CSV data
    for slot in unique_source_slots:
        protocol.load_labware(
        load_name="nest_96_wellplate_200ul_flat",
        location=slot
        )

    for index, row in enumerate(well_data[1::]):
    # get source location from CSV
        source_slot = row[0]
        
        source_well = row[1]
        source_location = protocol.deck[source_slot][source_well]

    # get volume as a number
        transfer_volume = float(row[4])

    # get destination location from CSV
        destination_slot = row[2]
        destination_well = row[3]
        destination_location = protocol.deck[destination_slot][destination_well]

    # perform parameterized transfer
    # trash=False will return tips to rack for practice
    # change to trash=True before starting actual experiment
        if transfer_volume <= 20:
                pipette.transfer(
                volume=transfer_volume,
                source=source_location,
                dest=destination_location,
                trash=False
            )
        else:
                pipette2.transfer(
                volume=transfer_volume,
                source=source_location,
                dest=destination_location,
                trash=False
            )