from __future__ import annotations

import pendulum
from airflow.utils.context import Context
from airflow.exceptions import AirflowSkipException
from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.utils.trigger_rule import TriggerRule
from airflow.operators.empty import EmptyOperator

# --- Conditional Logic Function to use in pre_execute ---
def check_if_first_run(context:Context):
    """
    Checks if the current run is the DAG's first scheduled run.
    If it is not the first run, it raises AirflowSkipException.
    This function is designed to be used as a `pre_execute` hook.
    """
    print("--- Running pre_execute: check_if_first_run ---")
    
    # Safely get dates from context
    logical_date = context['execution_date']
    dag_start_date = context["dag"].start_date
    
    print(f"Logical Date (from context): {logical_date}")
    print(f"DAG Start Date (from dag object): {dag_start_date}")

    # Compare in UTC to be absolutely safe across timezones
    if logical_date.in_timezone("UTC") != dag_start_date.in_timezone("UTC"):
        print("Decision: This is NOT the first run. Skipping.")
        raise AirflowSkipException("Skipping task: This is not the first run.")
    
    print("Decision: This IS the first run. Proceeding.")


def process_custom_date(**context):
    """
    This function receives a custom date via the 'params' dictionary
    and prints it to show it was passed correctly, independent of the
    DAG's logical_date.
    """
    print("--- Running python_callable: process_custom_date ---")
    
    # Access the custom date passed via the 'params' argument
    custom_date = context["params"].get("my_custom_date")
    
    if not custom_date:
        raise ValueError("Custom date was not passed in params!")
    
    print(f"Successfully received custom date from params: {custom_date}")
    print(f"For comparison, the DAG's logical date (ds) is: {context.get('ds')}")
    print("--- End of process_custom_date ---")

pipelines = {
    # ETL
    'etl_activity': {
        'action': 'etl',
        'layouts': 'gio/etl/jxm/activity_initial_load',
        'pre_execute': check_if_first_run,
        'log_date': "{{ ds }}"
    },
    # STD2
    'std_balance_snapshot': {
        'action': 'std2',
        'layouts': 'gio/std/jx1m/balance_snapshot_initial_load',
        'scope': 'monthly',
        'log_date': "{{ ((data_interval_end + macros.timedelta(hours=7).replace(day=1) - macros.timedelta(days=1)).strftime('%Y-%m-%d')) }}",
        'trigger_rule': TriggerRule.ALL_DONE
    }
}
default_args = {
    'start_date': pendulum.datetime(2025, 7, 12, tz="Asia/Ho_Chi_Minh")
}

# --- DAG DEFINITION ---
dag =  DAG(
    dag_id='test_first_run_and_custom_date',
    # Set a start_date a few days in the past to trigger catchup
    # default_args=default_args, 
    start_date=default_args['start_date'],
    # Run daily to easily test the logic
    schedule='@daily',
    catchup=True,
    tags=['testing', 'example'],
    doc_md="A simple DAG to test the 'run only once' pattern using pre_execute "
           "and passing a custom date to a downstream task."
)
start= EmptyOperator(task_id='start', dag=dag)
end= EmptyOperator(task_id='end', dag=dag)
# Task 1: A dummy task that uses the pre_execute hook to run only once.
one_time_setup_task = BashOperator(
    dag=dag,
    task_id='one_time_setup_with_pre_execute',
    bash_command='echo "This task should only run on the very first execution of the DAG."',
    pre_execute=check_if_first_run,
)

# Task 2: This task receives a custom date via `params`, mimicking your production DAG.
# It will run every time because of its trigger_rule.
process_date_task = PythonOperator(
    dag=dag,
    task_id='process_custom_date',
    python_callable=process_custom_date,
    params={
        # This is how you pass a custom, templated value.
        # It mimics the 'log_date' from your production pipeline config.
        'my_custom_date': "{{ data_interval_end.subtract(months=1).end_of('month').to_date_string() }}"
    },
    # This trigger rule is important. It ensures this task runs
    # even if the upstream `one_time_setup_task` is skipped on subsequent runs.
    trigger_rule=TriggerRule.ALL_DONE,
)

# --- Dependencies ---
start >> one_time_setup_task >> process_date_task >> end

