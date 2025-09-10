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
    
    # Run the script as a subprocess
    result = subprocess.run(
        ["python", script_path, ticket_id],
        capture_output=True,
        text=True,
        check=True # This will raise an exception if the script returns a non-zero exit code
    )
    
    print("Script output:")
    print(result.stdout)
    print(f"Successfully resolved ticket {ticket_id}.")