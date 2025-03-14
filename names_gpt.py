import os
import csv
from openai import OpenAI

# Set your OpenAI API key

def extract_company_name(filename):
    try:
        response = client.chat.completions.create(
            model="gpt-4o",  # Update the model as necessary
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": f"Extract the company name from the following filename: {filename}"}
            ]
        )
        company_name = response.choices[0].message.content.strip()
        return company_name
    except Exception as e:
        print(f"Error extracting company name: {e}")
        return None

# Directory containing the downloaded logos
download_folder = "downloaded_logos"
output_csv = "logo_mapping.csv"

# Open CSV file to write mappings
with open(output_csv, mode='w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(["filename", "company_name"])

    # Process each file in the directory
    for filename in os.listdir(download_folder):
        if filename.endswith('.svg'):  # Ensure we only process SVG files
            company_name = extract_company_name(filename)
            if company_name:
                writer.writerow([filename, company_name])
                print(f"Extracted company name for {filename}: {company_name}")
            else:
                print(f"Failed to extract company name for {filename}")

print("Company names extraction completed.")