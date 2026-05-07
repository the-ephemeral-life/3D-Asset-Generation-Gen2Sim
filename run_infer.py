import os
import paramiko
import sys
import time
import json

# =========================================================
# CONFIG - Remote GPU Inference Server
# =========================================================
HOST = "172.18.40.126" 
PORT = 22
USERNAME = "teaching"
PASSWORD = "import from env for personal use"

REMOTE_BASE = "/home/teaching/Desktop/stable-fast-3d"
REMOTE_INPUT_DIR = f"{REMOTE_BASE}/demo_files"
REMOTE_OUTPUT_DIR = f"{REMOTE_BASE}/output/0"

def run_remote_inference(local_input_path, local_output_glb_path):
    """
    Orchestrates the remote SSH connection to run Stable-Fast-3D.
    """
    # 1. SSH Connect
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    print(f"[*] Connecting to GPU server {HOST}...")
    ssh.connect(HOST, port=PORT, username=USERNAME, password=PASSWORD)
    
    # 2. SFTP Upload
    sftp = ssh.open_sftp()
    remote_input = f"{REMOTE_INPUT_DIR}/photo.png"
    remote_output = f"{REMOTE_OUTPUT_DIR}/mesh.glb"
    
    print(f"[*] Uploading {local_input_path}...")
    sftp.put(local_input_path, remote_input)
    
    # 3. Execution Command
    # We also extract inertial metadata using trimesh on the remote side
    remote_command = f"""
    cd {REMOTE_BASE}
    export PYTHONNOUSERSITE=1
    export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$CONDA_PREFIX/lib/python3.11/site-packages/nvidia/cusparse/lib:$CONDA_PREFIX/lib/python3.11/site-packages/nvidia/cublas/lib:$CONDA_PREFIX/lib/python3.11/site-packages/nvidia/cuda_runtime/lib:$CONDA_PREFIX/lib/python3.11/site-packages/nvidia/cudnn/lib:$CONDA_PREFIX/lib/python3.11/site-packages/nvidia/cusolver/lib:$CONDA_PREFIX/lib/python3.11/site-packages/nvidia/nvjitlink/lib:$LD_LIBRARY_PATH
    /home/teaching/anaconda3/envs/sf3d/bin/python run2.py demo_files/photo.png --output-dir output/
    
    # Extract Inertial Data
    /home/teaching/anaconda3/envs/sf3d/bin/python -c "
import trimesh
import json
m = trimesh.load('{remote_output}')
if hasattr(m, 'dump'): m = m.dump(concatenate=True)
print('---INERTIAL_START---')
print(json.dumps({{
    'mass': m.mass,
    'com': list(m.center_mass),
    'inertia': list(m.moment_inertia.flatten())
}}))
print('---INERTIAL_END---')
"
    """
    
    print("[*] Running remote inference (Stable-Fast-3D)...")
    stdin, stdout, stderr = ssh.exec_command(remote_command)
    
    full_output = ""
    for line in iter(stdout.readline, ""):
        print(line, end="")
        full_output += line
        
    exit_code = stdout.channel.recv_exit_status()
    if exit_code != 0:
        err = stderr.read().decode()
        print(f"[!] Remote Error: {err}")
        ssh.close()
        sys.exit(1)
        
    # 4. Download Result
    print(f"[*] Downloading result to {local_output_glb_path}...")
    sftp.get(remote_output, local_output_glb_path)
    
# 5. Cleanup
    sftp.close()
    ssh.close()
    
    # Extract inertial data from output
    try:
        if '---INERTIAL_START---' in full_output:
            data_str = full_output.split('---INERTIAL_START---')[1].split('---INERTIAL_END---')[0].strip()
            return json.loads(data_str)
    except Exception as e:
        print(f"[!] Failed to parse inertial data: {e}")
    
    return None

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python run_infer.py <input_image> <output_glb>")
        sys.exit(1)
    
    input_img = sys.argv[1]
    output_glb = sys.argv[2]
    
    inertial_data = run_remote_inference(input_img, output_glb)
    if inertial_data:
        # Print for the orchestrator to capture
        print("---METADATA_START---")
        print(json.dumps(inertial_data))
        print("---METADATA_END---")
