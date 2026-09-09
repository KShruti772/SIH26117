import pandas as pd

# Load the authorized maintenance.pdf into a DataFrame
df = pd.read_pdf('authorized_maintenance.pdf')

# Define the limits dictionary
limits = {
    'AOR': 100,
    'POR': 200
}

# Initialize a list to store findings
findings = []

# Iterate through the DataFrame to check for violations or exceedances
for index, row in df.iterrows():
    for equipment, limit in limits.items():
        measured_val = row[equipment]
        if isinstance(measured_val, (int, float)):
            if measured_val > limit:
                deviation = measured_val - limit
                findings.append({
                    'equipment': equipment,
                    'measured_value': measured_val,
                    'limit': limit,
                    'deviation': deviation,
                    'document_page': row['Page'],
                    'source_type': '[SOURCE_DOCUMENT_FACT]'
                })
        else:
            findings.append({
                'equipment': equipment,
                'measured_value': '[UNAVAILABLE_MEASUREMENT: ' + equipment + ']',
                'limit': limit,
                'deviation': None,
                'document_page': row['Page'],
                'source_type': '[SOURCE_DOCUMENT_FACT]'
            })

# Print the findings
for finding in findings:
    print(f"Equipment: {finding['equipment']}")
    print(f"Measured Value: {finding['measured_value']}")
    print(f"Documented Limit: {finding['limit']}")
    print(f"Deviation: {finding['deviation']}")
    print(f"Document Page: {finding['document_page']}")
    print(f"Source Type: {finding['source_type']}")
    print()