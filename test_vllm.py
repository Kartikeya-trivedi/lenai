import modal
import subprocess
import sys

app = modal.App("test-vllm")
vllm_image = modal.Image.debian_slim(python_version="3.11").pip_install("vllm")
rag_models_volume = modal.Volume.from_name("ktgpt-rag-models")

@app.function(image=vllm_image, gpu="A10G", volumes={"/models": rag_models_volume})
def test_start():
    print("Starting vLLM test...")
    cmd = [
        "python", "-m", "vllm.entrypoints.openai.api_server",
        "--model", "/models/llama-3.1-8b-instruct",
        "--port", "8000"
    ]
    # Run synchronously to capture output. It will crash or hang, but we'll see output if it crashes quickly.
    # To stream output in real-time if it hangs, we use Popen and stream lines.
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    
    for line in process.stdout:
        print(line, end="")
        
    process.wait()
    print("Process exited with code:", process.returncode)

if __name__ == "__main__":
    with app.run():
        test_start.remote()
