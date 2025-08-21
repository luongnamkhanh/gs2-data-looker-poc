# plugins/gsheet_uploader.py
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials

GCP_KEYFILE_PATH = "/opt/airflow/plugins/google_credentials.json"

def upload_dataframe(csv_path, gsheet_name):
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(GCP_KEYFILE_PATH, scope)
    client = gspread.authorize(creds)

    sheet = client.open(gsheet_name).sheet1
    sheet.clear()

    df = pd.read_csv(csv_path)

    sheet.update([df.columns.values.tolist()] + df.values.tolist())
    print(f"Successfully uploaded {len(df)} rows to '{gsheet_name}'.")