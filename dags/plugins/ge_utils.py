import great_expectations as gx
import pandas as pd
from great_expectations.core.batch import RuntimeBatchRequest
from airflow.exceptions import AirflowException


# The absolute path to your GE project inside the Airflow container
GE_PROJECT_DIR = "/opt/airflow/dags/gx"

def validate_dataframe(campaign_id: str, dataframe: pd.DataFrame, suite_name: str, task_instance=None):
    """
    Validates an in-memory Pandas DataFrame against a Great Expectations suite.
    """
    print(f"--- Starting Great Expectations validation against suite: {suite_name} ---")
    data_context = gx.get_context(context_root_dir=GE_PROJECT_DIR)

    # Note: A datasource is still needed in your great_expectations.yml for this to work.
    # The `great_expectations init` command should have created a default one.
    batch_request = RuntimeBatchRequest(
        datasource_name="my_filesystem_datasource", # Default name from `init`
        data_connector_name="default_runtime_data_connector_name",
        data_asset_name=f"{campaign_id}_dataframe",
        runtime_parameters={"batch_data": dataframe},
        batch_identifiers={"default_identifier_name": "default_identifier"},
    )

    validator = data_context.get_validator(
        batch_request=batch_request,
        expectation_suite_name=suite_name,
    )

    validation_result = validator.validate()

    if not validation_result["success"]:
        # Find all failed expectations and build a detailed error message
        failed_expectations = []
        for result in validation_result["results"]:
            if not result["success"]:
                failed_rule = result["expectation_config"]["expectation_type"]
                observed_value = result["result"].get("observed_value")
                kwargs = result["expectation_config"]["kwargs"]
                
                # Format a clear message for each failure
                error_msg = (
                    f"Validation Failed: {failed_rule}\n"
                    f"  > Expected: {kwargs}\n"
                    f"  > Observed: {observed_value}"
                )
                failed_expectations.append(error_msg)
        
        # Combine all failure messages into one
        all_failures = "\n".join(failed_expectations)

        if task_instance:
            task_instance.xcom_push(key="message_error", value=all_failures)
            
        raise AirflowException(
            f"Great Expectations validation failed!\n{all_failures}"
        )
    
    print("✅ Great Expectations validation successful!")

def load_and_validate_data(**kwargs):
    """
    Loads data from the path specified in the config, then validates the
    resulting DataFrame using the Great Expectations helper function.
    """
    data_path = kwargs['templates_dict']['data_path']
    suite_to_use = kwargs['templates_dict']['suite_name']
    campaign_id = kwargs['templates_dict']['campaign_id']
    task_instance = kwargs['ti']

    # In a real S3 setup, you would use a library like s3fs to read the file
    print(f"Loading data from: {data_path}")

    df = pd.read_csv(data_path)

    # Call the validation function from our plugin
    validate_dataframe(campaign_id=campaign_id, dataframe=df, suite_name=suite_to_use, task_instance=task_instance)

    # If validation passes, return the path for the next task.
    # If it fails, the function above will raise an error, failing this task.
    return True


def validate_dataframe_v2(campaign_id: str, dataframe: pd.DataFrame, suite_name: str, task_instance=None):
    """
    Validate a Pandas DataFrame using Great Expectations.
    If any expectation fails -> raise AirflowException (marks task as failed).
    """
    print(f"--- Starting Great Expectations validation against suite: {suite_name} ---")
    data_context = gx.get_context(context_root_dir=GE_PROJECT_DIR)

    batch_request = RuntimeBatchRequest(
        datasource_name="my_filesystem_datasource",
        data_connector_name="default_runtime_data_connector_name",
        data_asset_name=f"{campaign_id}_dataframe",
        runtime_parameters={"batch_data": dataframe},
        batch_identifiers={"default_identifier_name": "default_identifier"},
    )

    validator = data_context.get_validator(
        batch_request=batch_request,
        expectation_suite_name=suite_name,
    )

    validation_result = validator.validate()

    if not validation_result["success"]:
        failed_expectations = []
        for result in validation_result["results"]:
            if not result["success"]:
                failed_rule = result["expectation_config"]["expectation_type"]
                observed_value = result["result"].get("observed_value")
                kwargs = result["expectation_config"]["kwargs"]
                failed_expectations.append(
                    f"❌ {failed_rule}\n  > Expected: {kwargs}\n  > Observed: {observed_value}"
                )

        all_failures = "\n".join(failed_expectations)
        if task_instance:
            task_instance.xcom_push(key="message_error", value=all_failures)

        raise AirflowException(f"Great Expectations validation failed!\n{all_failures}")

    print("✅ Great Expectations validation successful!")

def load_validate_and_upload(**kwargs):
    """
    Combined task:
    - Load CSV
    - Validate using Great Expectations
    - Upload to Google Sheets (if validation passes)
    """
    templates = kwargs["templates_dict"]
    data_path = templates["data_path"]
    suite_name = templates["suite_name"]
    campaign_id = templates["campaign_id"]
    gsheet_name = templates["gsheet_name"]
    task_instance = kwargs["ti"]

    print(f"📥 Loading data from: {data_path}")
    df = pd.read_csv(data_path)

    # Validate the DataFrame
    try:
        validate_dataframe_v2(
            campaign_id=campaign_id,
            dataframe=df,
            suite_name=suite_name,
            task_instance=task_instance,
        )
    except AirflowException as e:
        print(f"❌ Validation failed: {e}")
        raise  # propagate the exception so Airflow marks the task as failed

    # If validation passes, upload to Google Sheets
    from plugins.gsheet_uploader import upload_dataframe
    print(f"📤 Validation passed. Uploading to Google Sheets: {gsheet_name}")
    try: 
        upload_dataframe(csv_path=data_path, gsheet_name=gsheet_name, ti=task_instance)

        print("✅ Task completed successfully.")

    except Exception as e:
        print(f"❌ Upload failed: {e}")
        raise AirflowException(f"Upload to Google Sheets failed: {e}")
    return True
