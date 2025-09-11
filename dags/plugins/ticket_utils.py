import os
import subprocess
import yaml
import re

def resolve_ticket(ticket_id: str):
    """
    Executes the resolve_ticket.py script as a subprocess.
    Requires CLIENT_ID and CLIENT_SECRET to be set as environment variables.
    """
    print(f"Attempting to resolve ticket {ticket_id}...")
    
    # The path to the script inside the Airflow container
    script_path = "/opt/airflow/dags/scripts/resolve_ticket.py"
    
    # # Run the script as a subprocess
    # result = subprocess.run(
    #     ["python", script_path, ticket_id],
    #     capture_output=True,
    #     text=True,
    #     check=True # This will raise an exception if the script returns a non-zero exit code
    # )
    
    # print("Script output:")
    # print(result.stdout)
    # print(f"Successfully resolved ticket {ticket_id}.")

    try:
        # Get credentials and prepare the environment for the subprocess
        script_env = os.environ.copy()
        script_env["CLIENT_ID"] = os.environ.get("CLIENT_ID")
        script_env["CLIENT_SECRET"] = os.environ.get("CLIENT_SECRET")

        if not all([script_env["CLIENT_ID"], script_env["CLIENT_SECRET"]]):
            raise ValueError("CLIENT_ID and CLIENT_SECRET environment variables must be set in Airflow.")

        # Run the script as a subprocess
        result = subprocess.run(
            ["python", script_path, ticket_id],
            capture_output=True,
            text=True,
            check=True, # This will raise an exception on non-zero exit
            env=script_env
        )
        
        print("Script STDOUT:")
        print(result.stdout)
        print(f"Successfully resolved ticket {ticket_id}.")

    except subprocess.CalledProcessError as e:
        # --- THIS IS THE NEW, ENHANCED LOGGING ---
        # This block will run if the script fails (returns exit code 1)
        print("❌ Subprocess script failed!")
        print(f"Return Code: {e.returncode}")
        print("--- captured STDOUT from script ---")
        print(e.stdout)
        print("--- captured STDERR from script ---")
        print(e.stderr)
        # Re-raise the exception to make the Airflow task fail as expected
        raise e