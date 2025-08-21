import yaml
from jinja2 import Environment, FileSystemLoader
import sys

# Get the config file path from the command line argument
config_path = sys.argv[1] # e.g., "gs2_configs/campaign_789.yaml"

# Load the config data from the YAML file
with open(config_path, "r") as f:
    config_data = yaml.safe_load(f)

# Set up the Jinja2 templating environment
env = Environment(loader=FileSystemLoader("templates/"))
template = env.get_template("dag_template.py.j2")

# Render the template with the config data
rendered_dag = template.render(config_data)

# Save the new DAG file
campaign_id = config_data["campaign_id"]
with open(f"dags/{campaign_id}_dag.py", "w") as f:
    f.write(rendered_dag)

print(f"Successfully generated dags/{campaign_id}_dag.py")