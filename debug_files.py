import modal
from modal_app import api_image, app

@app.function(image=api_image)
def check_files():
    import os
    print("Files in /root:", os.listdir("/root"))
    print("Files in /root/app:", os.listdir("/root/app"))
    import yaml
    try:
        with open("/root/model_registry.yaml") as f:
            print("YAML:", yaml.safe_load(f).keys())
    except Exception as e:
        print("Error reading YAML:", e)

@app.local_entrypoint()
def main():
    check_files.remote()
