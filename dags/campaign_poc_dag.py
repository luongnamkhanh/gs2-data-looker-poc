# templates/dag_template.py.j2
import pendulum
from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator
from plugins.gsheet_uploader import upload_dataframe # We will create this helper

with DAG(
    dag_id="campaign_poc_dag_1",
    start_date=pendulum.parse("2025-08-21"),
    schedule="@once",
    catchup=False,
    tags=["gs2", "generated"],
    is_paused_upon_creation = False
) as dag:

    # In a real scenario, a GreatExpectationsOperator would be here.
    # For the POC, we'll just simulate a successful validation.

    upload_to_gsheet = PythonOperator(
        task_id="upload_to_google_sheets",
        python_callable=upload_dataframe,
        op_kwargs={
            "csv_path": "dags/data/campaign_poc.csv",
            "gsheet_name": "My POC Airflow Sheet"
        }
    )