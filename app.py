import os
import sys
import json
import time
import subprocess
import shutil
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
import uvicorn

app = FastAPI(title="Gen2Sim Master Orchestrator")

# --- Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
BLENDER_PATH = "/opt/blender-4.5.4-linux-x64/blender"
REGISTRY_FILE = os.path.join(BASE_DIR, "spawned_objects.txt")

for d in [OUTPUTS_DIR, STATIC_DIR, UPLOAD_DIR]:
    os.makedirs(d, exist_ok=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Helper Functions ---

def generate_urdf(model_name, visual_path, collision_path, scale, mass, inertia, dim, com):
    """
    Generates a URDF file with stable box collision and real inertial data.
    """
    s3 = scale ** 3
    s5 = scale ** 5
    m_scaled = mass * s3
    i_scaled = [i * s5 for i in inertia]
    bx, by, bz = [d * scale for d in dim]
    z_offset = bz / 2.0
    com_x = com[0] * scale
    com_y = com[1] * scale
    com_z = (com[2] * scale) + z_offset

    urdf = f"""<?xml version="1.0" ?>
<robot name="{model_name}">
  <link name="base_link">
    <inertial>
      <origin xyz="{com_x} {com_y} {com_z}" rpy="0 0 0"/>
      <mass value="{m_scaled}"/>
      <inertia ixx="{i_scaled[0]}" ixy="{i_scaled[1]}" ixz="{i_scaled[2]}" iyy="{i_scaled[4]}" iyz="{i_scaled[5]}" izz="{i_scaled[8]}"/>
    </inertial>
    <visual>
      <origin xyz="0 0 {z_offset}" rpy="0 0 0"/>
      <geometry>
        <mesh filename="{visual_path}" scale="{scale} {scale} {scale}"/>
      </geometry>
    </visual>
    <collision>
      <origin xyz="0 0 {z_offset}" rpy="0 0 0"/>
      <geometry>
        <mesh filename="{collision_path}" scale="{scale} {scale} {scale}"/>
      </geometry>
    </collision>
  </link>
</robot>"""
    return urdf

def spawn_in_gazebo(urdf_path, model_name, x, y, z):
    """
    Calls ROS 2 ros_gz_sim to spawn the model.
    """
    cmd = [
        "ros2", "run", "ros_gz_sim", "create",
        "-file", urdf_path,
        "-name", model_name,
        "-allow_renaming", "true",
        "-x", str(x), "-y", str(y), "-z", str(z),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout, result.stderr

def get_offset_position(req_x, req_y, req_z, scale):
    """
    Simple collision avoidance for multiple spawns.
    """
    if not os.path.exists(REGISTRY_FILE):
        return req_x, req_y, req_z
    
    curr_x, curr_y = req_x, req_y
    padding = 0.2
    while True:
        collision = False
        with open(REGISTRY_FILE, "r") as f:
            for line in f:
                try:
                    px, py, ps = map(float, line.strip().split(','))
                    dist = ((curr_x - px)**2 + (curr_y - py)**2)**0.5
                    if dist < (scale + ps)/2 + padding:
                        collision = True
                        curr_x += (scale + ps)/2 + padding
                        break
                except: continue
        if not collision: break
    return curr_x, curr_y, req_z

# --- API Endpoints ---

@app.post("/api/reset")
async def reset_registry():
    if os.path.exists(REGISTRY_FILE):
        os.remove(REGISTRY_FILE)
    return {"message": "Registry reset."}

@app.post("/api/generate")
async def generate_pipeline(
    file: UploadFile = File(...),
    scale: float = Form(1.0),
    x: float = Form(0.0),
    y: float = Form(0.0),
    z: float = Form(1.0) # Default spawn Z to 1.0 to prevent clipping
):
    timestamp = int(time.time())
    obj_dir = os.path.join(OUTPUTS_DIR, f"object_{timestamp}")
    os.makedirs(obj_dir, exist_ok=True)
    
    # 1. Save input
    input_path = os.path.join(UPLOAD_DIR, f"{timestamp}_{file.filename}")
    with open(input_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
        
    async def pipeline_iterator():
        yield f"data: [*] Starting Gen2Sim Pipeline for {file.filename}\n\n"
        
        # 2. Run Inference
        yield "data: [*] Phase 1: Remote Inference (GPU Server)...\n\n"
        glb_path = os.path.join(obj_dir, "raw_mesh.glb")
        proc = subprocess.Popen(
            [sys.executable, "run_infer.py", input_path, glb_path],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        
        meta = None
        for line in iter(proc.stdout.readline, ""):
            if "---METADATA_START---" in line:
                meta_json = proc.stdout.readline().strip()
                try:
                    meta = json.loads(meta_json)
                    yield f"data: [*] Parsed physical metadata: Mass={meta['mass']:.4f}\n\n"
                except:
                    yield "data: [!] Failed to parse metadata JSON.\n\n"
                continue
            yield f"data: {line}\n\n"
        proc.wait()
        
        if proc.returncode != 0:
            yield "data: [!] Inference failed.\n\n"
            return

        # 3. Run Blender Processing
        yield "data: [*] Phase 2: Local Blender Processing (Baking & Normalization)...\n\n"
        blender_script = os.path.join(BASE_DIR, "text2.py")
        
        # Calculate object index for unique material naming
        try:
            obj_index = len([d for d in os.listdir(OUTPUTS_DIR) if os.path.isdir(os.path.join(OUTPUTS_DIR, d))])
        except:
            obj_index = 0
            
        blender_cmd = [
            BLENDER_PATH, "--background", "--python", blender_script, "--",
            glb_path, obj_dir, str(obj_index), str(timestamp)
        ]
        proc = subprocess.Popen(blender_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        
        dims = [1.0, 1.0, 1.0]
        for line in iter(proc.stdout.readline, ""):
            if "---DIMENSIONS_START---" in line:
                dim_str = proc.stdout.readline().strip()
                try:
                    dims = [float(d) for d in dim_str.split(",")]
                    yield f"data: [*] Parsed dimensions: {dims[0]:.2f}x{dims[1]:.2f}x{dims[2]:.2f}\n\n"
                except:
                    yield "data: [!] Failed to parse dimensions.\n\n"
                continue
            yield f"data: {line}\n\n"
        proc.wait()

        # 4. Generate URDF & Spawn
        yield "data: [*] Phase 3: Gazebo Integration (ROS 2 Jazzy)...\n\n"
        
        final_x, final_y, final_z = get_offset_position(x, y, z, scale)
        with open(REGISTRY_FILE, "a") as f:
            f.write(f"{final_x},{final_y},{scale}\n")

        visual_obj = os.path.join(obj_dir, "visual.obj")
        collision_obj = os.path.join(obj_dir, "collision.obj")
        
        mass = meta['mass'] if meta else 1.0
        inertia = meta['inertia'] if meta else [0.1, 0, 0, 0, 0.1, 0, 0, 0, 0.1]
        com = meta['com'] if meta else [0.0, 0.0, 0.0]
        
        urdf_content = generate_urdf(f"model_{timestamp}", "visual.obj", "collision.obj", scale, mass, inertia, dims, com)
        urdf_path = os.path.join(obj_dir, "model.urdf")
        with open(urdf_path, "w") as f: f.write(urdf_content)
        
        yield f"data: [*] Spawning at ({final_x:.2f}, {final_y:.2f}, {final_z:.2f})...\n\n"
        s_out, s_err = spawn_in_gazebo(urdf_path, f"gen2sim_{timestamp}", final_x, final_y, final_z)
        yield f"data: {s_out}\n\n"
        if s_err: yield f"data: [!] Gazebo Warning: {s_err}\n\n"

        # Final Asset Links
        assets = {
            "glb": f"/outputs/object_{timestamp}/raw_mesh.glb",
            "visual": f"/outputs/object_{timestamp}/visual.obj",
            "collision": f"/outputs/object_{timestamp}/collision.obj",
            "urdf": f"/outputs/object_{timestamp}/model.urdf",
            "texture": f"/outputs/object_{timestamp}/texture_{timestamp}.png"
        }
        yield f"data: ---ASSETS_START---{json.dumps(assets)}---ASSETS_END---\n\n"
        yield "data: [SUCCESS] Pipeline complete.\n\n"

    return StreamingResponse(pipeline_iterator(), media_type="text/event-stream")

app.mount("/outputs", StaticFiles(directory=OUTPUTS_DIR), name="outputs")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
