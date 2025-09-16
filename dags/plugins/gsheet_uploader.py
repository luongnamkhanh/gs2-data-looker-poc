# plugins/gsheet_uploader.py
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials

GCP_KEYFILE_PATH = "dags/plugins/google_credentials.json"

def upload_dataframe(csv_path, gsheet_name, **kwargs):
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        task_instance = kwargs.get('ti')
        creds = ServiceAccountCredentials.from_json_keyfile_name(GCP_KEYFILE_PATH, scope)
        client = gspread.authorize(creds)

        sheet = client.open(gsheet_name).sheet1
        sheet.clear()

        df = pd.read_csv(csv_path)

        sheet.update([df.columns.values.tolist()] + df.values.tolist())
        print(f"Successfully uploaded {len(df)} rows to '{gsheet_name}'.")
    except Exception as e:
        error_message = f"Failed to upload data to '{gsheet_name}': {str(e)}"
        print(error_message)
        if task_instance:
            task_instance.xcom_push(key="message_error", value=error_message)