import yaml
import sys
import re
import time
import hmac
import hashlib
import requests
import json
from dotenv import load_dotenv
import os

load_dotenv()

# This is a placeholder for how a signature might be generated.
# The actual logic must be provided by the API owner.
def generate_signature(timestamp, client_id, secret_key):
    """Generates a placeholder signature."""
    message = f"{client_id}{timestamp}"
    return hmac.new(secret_key.encode(), message.encode(), hashlib.sha256).hexdigest()

def get_ticket_details(ticket_id, client_id, client_secret):
    """
    Gets the full details for a given ticket ID.
    
    IMPORTANT: This function assumes the API endpoint for getting ticket details is
    at '.../service/v1/tickets/{ticket_id}'. You may need to verify this.
    """
    api_url = f"https://staging-ticket.vnggames.net/service/v1/tickets/{ticket_id}"
    timestamp = str(int(time.time()))
    signature = generate_signature(timestamp, client_id, client_secret)

    headers = {
        'x-client-id': client_id,
        'x-timestamp': timestamp,
        'x-signature': signature
    }
    print(f"▶️  Getting details for ticket ID {ticket_id}...")
    response = requests.get(api_url, headers=headers)
    response.raise_for_status()
    return response.json()


def main():
    if len(sys.argv) < 2:
        print("Usage: python validate_ticket.py <config_path>")
        sys.exit(1)

    config_path = sys.argv[1]
    client_id = os.getenv("CLIENT_ID")
    client_secret = os.getenv("CLIENT_SECRET")

    # --- 1. Load YAML and Extract Ticket ID ---
    try:
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)
        
        ticket_link = config_data.get("ticket_link")

        match = re.search(r'/(\d+)$', ticket_link)
        if not match:
            print(f"❌ ERROR: Could not parse ticket ID from URL: {ticket_link}")
            sys.exit(1)
        ticket_id = match.group(1)

    except Exception as e:
        print(f"❌ An unexpected error occurred while reading the config file: {e}")
        sys.exit(1)

    # --- 2. Get ticket details and validate status ---
    try:
        ticket_details = get_ticket_details(ticket_id, client_id, client_secret)

        # IMPORTANT: The following keys ('data', 'status', 'name') are assumptions
        # based on a typical API structure. You may need to adjust them.
        ticket_data = ticket_details.get("data", {})
        current_status = ticket_data.get("status", {}).get("name", "")

        print(f"ℹ️  Current ticket status is: '{current_status}'")

        if current_status.lower() != "in process":
            print(f"❌ ERROR: Ticket is not 'In Process'. Please update the ticket status before proceeding.")
            sys.exit(1)
        
        print("✅ Ticket validation successful: Status is 'In Process'.")
        sys.exit(0)

    except requests.exceptions.RequestException as e:
        print(f"❌ API request failed: {e}")
        sys.exit(1)
    except (json.JSONDecodeError, KeyError) as e:
        print(f"❌ Failed to parse a valid JSON response or expected key not found: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()