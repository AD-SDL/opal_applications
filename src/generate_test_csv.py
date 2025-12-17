#A test input to the protocol imagining 3 source plates of 16 reagents + water, 1 destination plate with adjustable number of samples
import random
import pandas as pd
columns = ["Source_Plate", "Source_Well", "Dest_Plate", "Dest_Well", "Transfer_Vol"]
output_data = pd.DataFrame(columns=columns)
source_plates = ["A1", "A2", "A3"]
destination_plate = "B1"
num_reagents = 17
num_samples = 18
for i in range(num_reagents):
    source_well = f"{chr(65 + (i % 8))}{(i // 8) + 1}"
    for j in range(num_samples):
        dest_well = f"{chr(65 + (j % 8))}{(j // 8) + 1}"
        volume = random.randrange(1, 300)
        source_plate = source_plates[i // 8]
        output_data.loc[len(output_data)] = [source_plate,source_well,destination_plate, dest_well,volume]
        
        
output_data.to_csv("../csv_outputs/OTFlex_test.csv", index=False)
        
