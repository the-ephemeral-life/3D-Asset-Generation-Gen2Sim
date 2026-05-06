import os
import paramiko
import sys
import subprocess
import time

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
    except ValueError: pass

# Get requested coordinates from 3rd, 4th, 5th arguments
REQ_X, REQ_Y, REQ_Z = 0.0, 0.0, 0.5
if len(sys.argv) > 5:
    try:
        REQ_X = float(sys.argv[3])
        REQ_Y = float(sys.argv[4])
        REQ_Z = float(sys.argv[5])
    except ValueError: pass

# Unique filename to prevent Gazebo caching issues and allow multiple spawns
TIMESTAMP = int(time.time())
LOCAL_OUTPUT = f"/home/himank/Desktop/mesh_{TIMESTAMP}.glb"
REGISTRY_FILE = "/home/himank/Desktop/Project/spawned_objects.txt"

def get_final_position(target_x, target_y, target_z, scale):
    if not os.path.exists(REGISTRY_FILE):
        return target_x, target_y, target_z
    
    current_x, current_y, current_z = target_x, target_y, target_z
    padding = 0.2 # Small gap between objects
    
    while True:
        collision = False
        with open(REGISTRY_FILE, "r") as f:
            for line in f:
                try:
                    line = line.strip()
                    if not line: continue
                    px, py, ps = map(float, line.split(','))
                    # Check for overlap in XY plane
                    dist_x = abs(current_x - px)
                    dist_y = abs(current_y - py)
                    min_dist = (scale + ps) / 2.0 + padding
                    
                    if dist_x < min_dist and dist_y < min_dist:
                        collision = True
                        current_x += min_dist # Shift right
                        break
                except Exception as e:
                    print(f"Error parsing registry line: {e}")
                    continue
        if not collision:
            break
    return current_x, current_y, current_z

FINAL_X, FINAL_Y, FINAL_Z = get_final_position(REQ_X, REQ_Y, REQ_Z, MODEL_SCALE)

# Save the new position to registry
with open(REGISTRY_FILE, "a") as f:
    f.write(f"{FINAL_X},{FINAL_Y},{MODEL_SCALE}\n")

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
print(f"Spawning model '{TIMESTAMP}' in Gazebo at ({FINAL_X}, {FINAL_Y}, {FINAL_Z})...")

model_name = f"spawned_mesh_{TIMESTAMP}"

# User requested orientation: 1.57 0 0
# Explicitly passing these via command line flags is more reliable in ros_gz_sim
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
    "-x", str(FINAL_X),
    "-y", str(FINAL_Y),
    "-z", str(FINAL_Z),
    "-R", "1.57",
    "-P", "0",
    "-Y", "0"
]

try:
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    print("Successfully spawned in Gazebo.")
    print(result.stdout)
except subprocess.CalledProcessError as e:
    print(f"Failed to spawn in Gazebo: {e}")
    print(f"Stdout: {e.stdout}")
    print(f"Stderr: {e.stderr}")
except FileNotFoundError:
    print("ros2 command not found. Ensure ROS 2 and ros_gz_sim are sourced.")
