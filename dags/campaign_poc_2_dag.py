# templates/dag_template.py.j2
import pendulum
from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator

# Import the helper functions from the plugins folder
from plugins.gsheet_uploader import upload_dataframe
from plugins.ticket_utils import resolve_ticket

with DAG(
    dag_id="campaign_poc_2_dag",
    start_date=pendulum.parse("2025-08-21"),
    schedule="@once",
    catchup=False,
    is_paused_upon_creation=False,
    tags=["gs2", "generated"],
) as dag:

    # In a real scenario, a GreatExpectationsOperator would be here.
    # For the POC, we'll just simulate a successful validation.

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
            "ticket_id": "21656"
        }
    )

    # Define the new task order
    upload_to_gsheet >> resolve_ticket_task