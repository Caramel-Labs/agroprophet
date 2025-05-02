

import pandas as pd
import sqlite3
import os
import sys

# Add the project root directory to the system path to import settings
# Adjust '../' if settings.py is located differently relative to this script
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../'))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

try:
    from settings import DB_PATH
    print(f"Database path loaded from settings: {DB_PATH}")
except ImportError:
    print("Error: Could not import DB_PATH from settings. Make sure settings.py is accessible.")
    sys.exit(1) # Exit if settings cannot be loaded

# --- Configuration ---
# Path to your historical price data CSV file
CSV_FILE_PATH = '../dataset/train_data.csv' # <--- Adjust this path if your CSV is elsewhere

# Define the expected column names in your CSV file
# These should match the data you want to insert into the 'price' table
CSV_COLUMNS = ['Date', 'Region', 'Commodity', 'Price per Unit (Silver Drachma/kg)']

# Define the mapping between CSV columns and DB columns
CSV_TO_DB_MAPPING = {
    'Date': 'date',
    'Region': 'region',
    'Commodity': 'crop',  # This is the key fix - mapping Commodity to crop
    'Price per Unit (Silver Drachma/kg)': 'price'
}
# --- End Configuration ---

def import_price_data_from_csv(csv_path: str, db_path: str):
    """
    Reads historical price data from a CSV file and imports it into the
    'price' table in the SQLite database, marking entries as actual data.
    """
    if not os.path.exists(csv_path):
        print(f"Error: CSV file not found at '{csv_path}'")
        return

    # Ensure the database directory exists
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
        print(f"Created database directory: {db_dir}")

    try:
        print(f"Reading data from '{csv_path}'...")
        # Read the CSV file into a pandas DataFrame
        df = pd.read_csv(csv_path)

        # Basic validation: Check if required columns exist in the CSV
        if not all(col in df.columns for col in CSV_COLUMNS):
            missing_cols = [col for col in CSV_COLUMNS if col not in df.columns]
            print(f"Error: CSV file must contain the following columns: {CSV_COLUMNS}")
            print(f"Missing columns: {missing_cols}")
            print(f"Columns found in CSV: {df.columns.tolist()}")
            return

        # Select only the required columns and handle potential extra columns in CSV
        df = df[CSV_COLUMNS]

        print(f"Successfully read {len(df)} rows from CSV. Preparing data for database...")

        # Rename columns to match database column names
        # This step avoids confusion between CSV and DB column names
        df_renamed = df.rename(columns=CSV_TO_DB_MAPPING)
        
        # Add the 'actual' column with value 1 for all historical records
        df_renamed['actual'] = 1
        
        # Prepare data for insertion, ensuring order matches the SQL statement
        data_to_insert = df_renamed[['date', 'region', 'crop', 'price', 'actual']].to_numpy().tolist()

        if not data_to_insert:
            print("No data rows found in CSV to import.")
            return

        print(f"Attempting to insert {len(data_to_insert)} rows into the 'price' table...")

        # Connect to the database
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            # Use executemany for efficient bulk insertion
            # Use INSERT OR IGNORE to skip rows that would violate the UNIQUE(date, region, crop) constraint
            # This is helpful if you run the script multiple times or have partial data already.
            try:
                cursor.executemany(
                    """
                    INSERT OR IGNORE INTO price (date, region, crop, price, actual)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    data_to_insert
                )

                # Commit the transaction
                conn.commit()
                # Note: cursor.rowcount after INSERT OR IGNORE with executemany might be -1 or inconsistent
                # depending on the SQLite version and driver. It's safer to report total attempted.
                print(f"Import complete. Attempted to process {len(data_to_insert)} rows.")
                print("Historical data import finished.")

            except sqlite3.Error as e:
                print(f"Database error during import: {e}")
                conn.rollback() # Roll back in case of error

        print("Database connection closed.")

    except FileNotFoundError:
         # This should be caught by the initial check, but good to have here too
         print(f"Error: CSV file not found at '{csv_path}'")
    except pd.errors.EmptyDataError:
         print(f"Error: CSV file is empty at '{csv_path}'. No data to import.")
    except pd.errors.ParserError:
         print(f"Error: Could not parse CSV file at '{csv_path}'. Check its format and columns.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


# This block ensures the import function runs only when the script is executed directly
if __name__ == "__main__":
    print("--- Starting Historical Data Import Script ---")
    import_price_data_from_csv(CSV_FILE_PATH, DB_PATH)
    print("--- Script Finished ---")