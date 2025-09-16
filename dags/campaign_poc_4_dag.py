# templates/dag_template.py.j2
import pendulum
from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
import pandas as pd

# Import the helper functions from the plugins folder
from plugins.gsheet_uploader import upload_dataframe
from plugins.ticket_utils import resolve_ticket
from plugins.ge_utils import load_and_validate_data
from plugins.dag_logger import log_start, log_end, on_failure_callback

with DAG(
    dag_id="campaign_poc_4_dag",
    start_date=pendulum.parse("2025-08-20"),
    schedule="@once",
    catchup=False,
    is_paused_upon_creation=False,
    tags=["gs2", "generated", "gx"],
    on_success_callback=log_end,
    on_failure_callback=on_failure_callback
) as dag:

    start = PythonOperator(
        task_id="start",
        python_callable=log_start,
    )

    load_and_validate = PythonOperator(
        task_id="load_and_validate_data",
        python_callable=load_and_validate_data,
        templates_dict={
            "campaign_id": "campaign_poc_4",
            "data_path": "dags/data/campaign_poc_2.csv",
            "suite_name": "my_first_suite" # Use the suite we created
        }
    )

    upload_to_gsheet = PythonOperator(
        task_id="upload_to_google_sheets",
        python_callable=upload_dataframe,
        op_kwargs={
            "csv_path": "dags/data/campaign_poc_2.csv",
            "gsheet_name": "My POC Airflow Sheet"
        }
    )

    resolve_ticket_task = PythonOperator(
        task_id="resolve_mytool_ticket",
        python_callable=resolve_ticket,
        # Pass the ticket ID from the previous task using XComs
        op_kwargs={
            "ticket_id": "22081"
        }
    )

    end = EmptyOperator(task_id="End") 

    # Define the new task order
    start >> load_and_validate >> upload_to_gsheet >> resolve_ticket_task >> end