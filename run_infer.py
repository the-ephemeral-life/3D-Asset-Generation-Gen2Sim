import os
import paramiko
import sys

# =========================
# CONFIG
# =========================
HOST = "172.18.40.126"
PORT = 22
USERNAME = "teaching"
PASSWORD = "ds123"   

REMOTE_BASE = "/home/teaching/Desktop/stable-fast-3d"
REMOTE_INPUT_DIR = f"{REMOTE_BASE}/demo_files"
REMOTE_OUTPUT_DIR = f"{REMOTE_BASE}/output/0"

# Use command line argument if provided, else fallback to default
if len(sys.argv) > 1:
    LOCAL_INPUT = sys.argv[1]
    print(f"Using input image: {LOCAL_INPUT}")
else:
    LOCAL_INPUT = "/home/himank/Desktop/chair.jpg"
    print(f"Using default input image: {LOCAL_INPUT}")

# Get scale from second argument, default to 1.0
MODEL_SCALE = 1.0
if len(sys.argv) > 2:
    try:
        MODEL_SCALE = float(sys.argv[2])
        print(f"Target model size: {MODEL_SCALE} meters")
    except ValueError:
        print("Invalid scale provided, defaulting to 1.0")

LOCAL_OUTPUT = "/home/himank/Desktop/mesh.glb"

REMOTE_INPUT = f"{REMOTE_INPUT_DIR}/photo.png"
REMOTE_OUTPUT = f"{REMOTE_OUTPUT_DIR}/mesh.glb"

# =========================
# REMOTE COMMAND
# =========================
REMOTE_COMMAND = """
cd /home/teaching/Desktop/stable-fast-3d
export PYTHONNOUSERSITE=1
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$CONDA_PREFIX/lib/python3.11/site-packages/nvidia/cusparse/lib:$CONDA_PREFIX/lib/python3.11/site-packages/nvidia/cublas/lib:$CONDA_PREFIX/lib/python3.11/site-packages/nvidia/cuda_runtime/lib:$CONDA_PREFIX/lib/python3.11/site-packages/nvidia/cudnn/lib:$CONDA_PREFIX/lib/python3.11/site-packages/nvidia/cusolver/lib:$CONDA_PREFIX/lib/python3.11/site-packages/nvidia/nvjitlink/lib:$LD_LIBRARY_PATH
/home/teaching/anaconda3/envs/sf3d/bin/python run2.py demo_files/photo.png --output-dir output/
"""

# =========================
# SSH CONNECT
# =========================
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

print("Connecting to remote server...")
ssh.connect(HOST, port=PORT, username=USERNAME, password=PASSWORD)

# =========================
# SFTP UPLOAD
# =========================
sftp = ssh.open_sftp()

print("Uploading image...")
sftp.put(LOCAL_INPUT, REMOTE_INPUT)

# =========================
# RUN REMOTE MODEL
# =========================
print("Running remote inference...")
stdin, stdout, stderr = ssh.exec_command(REMOTE_COMMAND)

exit_code = stdout.channel.recv_exit_status()

out = stdout.read().decode()
err = stderr.read().decode()

print(out)

if exit_code != 0:
    print("Remote error:")
    print(err)
    sftp.close()
    ssh.close()
    raise RuntimeError("Remote inference failed")

# =========================
# DOWNLOAD RESULT
# =========================
print("Downloading GLB...")
sftp.get(REMOTE_OUTPUT, LOCAL_OUTPUT)

# =========================
# CLEANUP
# =========================
sftp.close()
ssh.close()

print(f"Done. Output saved to: {LOCAL_OUTPUT}")

# =========================
# SPAWN IN GAZEBO
# =========================
import subprocess
import time

print("Spawning model in Gazebo...")

model_name = f"spawned_mesh_{int(time.time())}"
sdf_content = f"""<?xml version="1.0" ?>
<sdf version="1.6">
  <model name="{model_name}">
    <static>false</static>
    <link name="link">
      <visual name="visual">
        <geometry>
          <mesh>
            <uri>file://{LOCAL_OUTPUT}</uri>
            <scale>{MODEL_SCALE} {MODEL_SCALE} {MODEL_SCALE}</scale>
          </mesh>
        </geometry>
      </visual>
      <collision name="collision">
        <geometry>
          <mesh>
            <uri>file://{LOCAL_OUTPUT}</uri>
            <scale>{MODEL_SCALE} {MODEL_SCALE} {MODEL_SCALE}</scale>
          </mesh>
        </geometry>
      </collision>
    </link>
  </model>
</sdf>"""

cmd = [
    "ros2", "run", "ros_gz_sim", "create",
    "-string", sdf_content,
    "-name", model_name,
    "-allow_renaming", "true",
    "-z", "0.5"
]

try:
    subprocess.run(cmd, check=True)
    print("Successfully spawned in Gazebo.")
except subprocess.CalledProcessError as e:
    print(f"Failed to spawn in Gazebo: {e}")
except FileNotFoundError:
    print("ros2 command not found. Ensure ROS 2 and ros_gz_sim are sourced.")