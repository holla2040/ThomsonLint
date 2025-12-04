import json
import jsonschema
import os

def validate_json(json_file_path, schema_file_path):
    try:
        with open(json_file_path, 'r') as f:
            json_data = json.load(f)
        with open(schema_file_path, 'r') as f:
            schema_data = json.load(f)
        
        jsonschema.validate(instance=json_data, schema=schema_data)
        print(f"Validation successful for {json_file_path} against {schema_file_path}")
        return True
    except jsonschema.exceptions.ValidationError as e:
        print(f"Validation failed for {json_file_path} against {schema_file_path}:")
        print(e)
        return False
    except FileNotFoundError:
        print(f"Error: One of the files not found. Check paths: {json_file_path}, {schema_file_path}")
        return False
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON file {json_file_path}: {e}")
        return False

if __name__ == "__main__":
    ontology_json = 'ontology/ontology.json'
    ontology_schema = 'tests/ontology_schema.json'
    examples_json = 'examples/examples.json'
    examples_schema = 'tests/examples_schema.json'

    # Validate ontology.json
    print(f"Validating {ontology_json}...")
    ontology_valid = validate_json(ontology_json, ontology_schema)
    print("-" * 30)

    # Validate examples.json
    print(f"Validating {examples_json}...")
    examples_valid = validate_json(examples_json, examples_schema)
    print("-" * 30)

    if ontology_valid and examples_valid:
        print("All JSON files validated successfully.")
    else:
        print("Some JSON files failed validation.")
