# templates/dag_template.py.j2
import pendulum
from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator

# Import the helper functions from the plugins folder
from plugins.gsheet_uploader import upload_dataframe
from plugins.ticket_utils import resolve_ticket
from plugins.ge_utils import validate_dataframe

def load_and_validate_data(**kwargs):
    """
    Loads data from the path specified in the config, then validates the
    resulting DataFrame using the Great Expectations helper function.
    """
    data_path = kwargs['templates_dict']['data_path']
    suite_to_use = kwargs['templates_dict']['suite_name']
    
    # In a real S3 setup, you would use a library like s3fs to read the file
    print(f"Loading data from: {data_path}")
    
    df = pd.read_csv(data_path)
    
    # Call the validation function from our plugin
    validate_dataframe(dataframe=df, suite_name=suite_to_use)
    
    # If validation passes, return the path for the next task.
    # If it fails, the function above will raise an error, failing this task.
    return True

with DAG(
    dag_id="campaign_poc_4_dag",
    start_date=pendulum.parse("2025-08-21"),
    schedule="@once",
    catchup=False,
    is_paused_upon_creation=False,
    tags=["gs2", "generated"],
) as dag:

    load_and_validate = PythonOperator(
        task_id="load_and_validate_data",
        python_callable=load_and_validate_data,
        templates_dict={
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

    # Define the new task order
    load_and_validate >> upload_to_gsheet >> resolve_ticket_task