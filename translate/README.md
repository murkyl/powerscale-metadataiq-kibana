# translate
This script to translate Kibana dashboard panels into languages other than English.

### Dependencies
None

## Execution

### Run the script
python3 translate.py --lang=en templates/metadata_panels.ndjson output_file.ndjson

## Data format
The translated string are found in individual JSON files in the 'translations' directory. Each JSON file consists follows the i18next JSON format. Currently only basic keys are used. There are 3 main key subtypes: description, label, and title. These subtypes correspond to the key name used in the Kibana NDJSON panels themselves.

Example from a partial panel:
  "e1a729de-7780-4117-81c3-98d9374b9e5a": {
    "customLabel": true,
    "dataType": "string",
    "isBucketed": true,
    "label": "Cluster names",
    "operationType": "terms",

In the example above, the key "label" has a value of "Cluster names". This value is the key used in the translation file.

Example translation file:
{
  "labels": {
    "Cluster names": "クラスタ名"
  }
}

This translation file would change all labels, in a Kibana panel, where the value is "Cluster names" to "クラスタ名".

## Issues, bug reports, and suggestions
For any issues with the script, please re-run the script with debug enabled (--debug command line option) and open an issue with the debug output and description of the problem.
