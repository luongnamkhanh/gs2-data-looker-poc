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

# This is a placeholder for how a signature might be generated.
# The actual logic must be provided by the API owner.
def generate_signature(timestamp, client_id, secret_key):
    """Generates a placeholder signature."""
    message = f"{client_id}|{timestamp}|{secret_key}"
    return hashlib.md5(message.encode('utf-8')).hexdigest()

def get_ticket_actions(ticket_id, client_id, client_secret):
    """Gets the list of available actions for a ticket."""
    api_url = f"https://staging-ticket.vnggames.net/service/v1/tickets/{ticket_id}/actions"
    timestamp = str(int(time.time()))
    signature = generate_signature(timestamp, client_id, client_secret)

    headers = {
        'x-client-id': client_id,
        'x-timestamp': timestamp,
        'x-signature': signature
    }
    print(f"▶️  Getting available actions for ticket ID {ticket_id}...")
    response = requests.get(api_url, headers=headers)
    response.raise_for_status()
    return response.json()

def perform_ticket_action(ticket_id, action_id, client_id, client_secret):
    """Performs a specific action on a ticket."""
    api_url = "https://staging-ticket.vnggames.net/service/v1/listen"
    timestamp = str(int(time.time()))
    signature = generate_signature(timestamp, client_id, client_secret)

    headers = {
        'x-client-id': client_id,
        'x-timestamp': timestamp,
        'x-signature': signature,
        'Content-Type': 'application/json'
    }
    
    payload = {
        "ticket_id": int(ticket_id),
        "action_type": "do:action",
        "data": {
            "action_id": action_id
        }
    }
    print(f"▶️  Performing action ID {action_id} on ticket ID {ticket_id}...")
    response = requests.post(api_url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()

def main():
    if len(sys.argv) < 2:
        print("Usage: python resolve_ticket.py <config_path>")
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

    # --- 2. Find the 'Resolve' action ID and execute it ---
    try:
        actions_response = get_ticket_actions(ticket_id, client_id, client_secret)
        actions = actions_response.get("data", [])
        
        resolve_action_id = None
        for action in actions:
            if action.get("name", "").lower() == "resolve":
                resolve_action_id = action.get("id")
                break
        
        if not resolve_action_id:
            print("❌ Could not find the 'Resolve' action. Available actions:", [a.get("name") for a in actions])
            sys.exit(1)

        print(f"✅ Found 'Resolve' action with ID: {resolve_action_id}")
        
        # Perform the action
        resolve_response = perform_ticket_action(ticket_id, resolve_action_id, client_id, client_secret)
        
        if resolve_response.get("code") == "SUCCESS":
            print(f"✅ Successfully resolved ticket {ticket_id}.")
            sys.exit(0)
        else:
            print(f"❌ Failed to resolve ticket. Response: {resolve_response}")
            sys.exit(1)

    except requests.exceptions.RequestException as e:
        print(f"❌ API request failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()