import great_expectations as gx
import pandas as pd
from great_expectations.core.batch import RuntimeBatchRequest
from airflow.exceptions import AirflowException

# The absolute path to your GE project inside the Airflow container
GE_PROJECT_DIR = "/opt/airflow/dags/gx"

def validate_dataframe(campaign_id: str, dataframe: pd.DataFrame, suite_name: str):
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
        raise AirflowException("Great Expectations validation failed!")
    
    print("✅ Great Expectations validation successful!")