import yaml
import json
import sys
from jsonschema import validate, ValidationError

SCHEMA_PATH = "config_schema.json"

def main():
    # The CICD pipeline will pass the path to the new/changed YAML file
    if len(sys.argv) < 2:
        print("Usage: python validate_config.py <path_to_config_file>")
        sys.exit(1)

    config_file_path = sys.argv[1]

    try:
        # 1. Load the schema (our rulebook)
        with open(SCHEMA_PATH, 'r') as f:
            schema = json.load(f)

        # 2. Load the GS2 config file we want to check
        with open(config_file_path, 'r') as f:
            config_data = yaml.safe_load(f)

        # 3. This is the magic step! It validates the data against the schema.
        #    If anything is wrong, it raises a ValidationError.
        validate(instance=config_data, schema=schema)

        print(f"✅ Validation successful for: {config_file_path}")
        sys.exit(0) # Exit with success code

    except FileNotFoundError as e:
        print(f"❌ ERROR: File not found - {e}")
        sys.exit(1)
    except ValidationError as e:
        print(f"❌ VALIDATION FAILED for {config_file_path}:")
        print(f"   Error: {e.message}")
        print(f"   Location: {' -> '.join(map(str, e.path))}")
        sys.exit(1) # Exit with failure code
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()