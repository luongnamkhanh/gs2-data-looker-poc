import pytz
from datetime import datetime
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.utils.context import Context

# Use the default connection ID for the Airflow metadata database
AIRFLOW_DB_CONN_ID = "airflow_db"

def log_start(**kwargs):
    """Inserts a new log entry for the DAG run, marking it as 'Fail' by default."""
    dag_id = kwargs["dag"].dag_id
    start_date = (
        datetime.now()
        .astimezone(pytz.timezone("Asia/Ho_Chi_Minh"))
        .strftime("%Y-%m-%d %H:%M:%S.%f")
    )
    status = "Fail"
    sql_query = f"""INSERT INTO dag_run_log (dag_id, start_date, status) 
    VALUES ('{dag_id}', '{start_date}', '{status}');"""

    # Use PostgresHook and the default Airflow DB connection
    pg_hook = PostgresHook(postgres_conn_id=AIRFLOW_DB_CONN_ID)
    pg_hook.run(sql_query)


def log_end(**kwargs):
    """Finds the latest log entry for this DAG and updates its status to 'Success'."""
    dag_id = kwargs["dag"].dag_id
    end_date = (
        datetime.now()
        .astimezone(pytz.timezone("Asia/Ho_Chi_Minh"))
        .strftime("%Y-%m-%d %H:%M:%S.%f")
    )
    status = "Success"
    
    # Use standard Postgres SQL syntax for the update
    sql_query = f"""
    UPDATE dag_run_log 
    SET end_date = '{end_date}', status = '{status}'
    WHERE id = (
        SELECT MAX(id) 
        FROM dag_run_log 
        WHERE dag_id = '{dag_id}'
    );
    """

    pg_hook = PostgresHook(postgres_conn_id=AIRFLOW_DB_CONN_ID)
    pg_hook.run(sql_query)
    

def on_failure_callback(context: Context):
    """Finds the latest log entry and updates it with the failure message."""
    dag_id = context.get("dag").dag_id
    end_date = (
        datetime.now()
        .astimezone(pytz.timezone("Asia/Ho_Chi_Minh"))
        .strftime("%Y-%m-%d %H:%M:%S.%f")
    )
    
    task_instance = context["task_instance"]
    
    # Try to get the detailed error message from Great Expectations (pushed to XCom)
    error_message = task_instance.xcom_pull(
        task_ids=task_instance.task_id, key="message_error"
    )
    
    # If no custom message, get the standard Python exception
    if not error_message:
        error_message = str(context.get("exception"))

    error_message = error_message.replace("'", "''")  # Basic SQL escaping

    # Use standard Postgres SQL syntax for the update
    sql_query = f"""
    UPDATE dag_run_log 
    SET end_date = '{end_date}', message = '{error_message}'
    WHERE id = (
        SELECT MAX(id) 
        FROM dag_run_log 
        WHERE dag_id = '{dag_id}'
    );
    """
    pg_hook = PostgresHook(postgres_conn_id=AIRFLOW_DB_CONN_ID)
    pg_hook.run(sql_query)