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

def find_findings_files():
    """Find *-findings.json files in the exports/ directory."""
    findings_dir = 'exports'
    if not os.path.isdir(findings_dir):
        return []
    return [
        os.path.join(findings_dir, f)
        for f in os.listdir(findings_dir)
        if f.endswith('-findings.json')
    ]


if __name__ == "__main__":
    import sys

    ontology_json = 'ontology/ontology.json'
    ontology_schema = 'tests/ontology_schema.json'
    examples_json = 'examples/examples.json'
    examples_schema = 'tests/examples_schema.json'
    findings_schema = 'tests/findings_schema.json'

    all_valid = True

    # Validate ontology.json
    print(f"Validating {ontology_json}...")
    if not validate_json(ontology_json, ontology_schema):
        all_valid = False
    print("-" * 30)

    # Validate examples.json
    print(f"Validating {examples_json}...")
    if not validate_json(examples_json, examples_schema):
        all_valid = False
    print("-" * 30)

    # Validate findings JSON files (from exports/ or command-line arguments)
    findings_files = find_findings_files()
    extra_args = [a for a in sys.argv[1:] if a.endswith('.json')]
    findings_files.extend(extra_args)

    for fpath in findings_files:
        print(f"Validating findings: {fpath}...")
        if not validate_json(fpath, findings_schema):
            all_valid = False
        print("-" * 30)

    if all_valid:
        print("All JSON files validated successfully.")
    else:
        print("Some JSON files failed validation.")
