# templates/dag_template.py.j2
import pendulum
from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator
import pandas as pd

# Import the helper functions from the plugins folder
from plugins.gsheet_uploader import upload_dataframe
from plugins.ticket_utils import resolve_ticket
from plugins.ge_utils import load_and_validate_data, load_validate_and_upload
from plugins.dag_logger import log_start, log_end, on_failure_callback

with DAG(
    dag_id="campaign_poc_5_dag",
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

    validate_and_upload = PythonOperator(
        task_id="validate_and_upload",
        python_callable=load_validate_and_upload,
        templates_dict={
            "campaign_id": "campaign_poc_5",
            "data_path": "dags/data/campaign_poc_2.csv",
            "suite_name": "my_first_suite",
            "gsheet_name": "My POC Airflow Sheet"
        },
    )

    resolve_ticket_task = PythonOperator(
        task_id="resolve_mytool_ticket",
        python_callable=resolve_ticket,
        # Pass the ticket ID from the previous task using XComs
        op_kwargs={
            "ticket_id": "22081"
        }
    )

    end = EmptyOperator(task_id="end") 

    # Define the new task order
    start >> validate_and_upload >> resolve_ticket_task >> end