import json
import glob

def clean_settings(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except Exception:
            return
            
    if 'settings' in data and isinstance(data['settings'], dict):
        allowed_keys = {
            "executionOrder", "saveDataErrorExecution", "saveDataSuccessExecution",
            "saveManualExecutions", "callerPolicy", "errorWorkflow", "timezone"
        }
        clean = {k: v for k, v in data['settings'].items() if k in allowed_keys}
        data['settings'] = clean
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Cleaned settings in {filepath}")

for f in glob.glob('n8n-workflows/*.json'):
    clean_settings(f)
