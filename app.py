from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import subprocess
import shutil
import os
import uuid

app = FastAPI()

# Setup directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
STATIC_DIR = os.path.join(BASE_DIR, "static")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

@app.post("/api/reset")
async def reset_world():
    registry_path = os.path.join(BASE_DIR, "spawned_objects.txt")
    if os.path.exists(registry_path):
        os.remove(registry_path)
    return {"status": "success", "message": "Spawning registry reset."}

@app.post("/api/generate")
async def generate_model(
    file: UploadFile = File(...),
    dimension: float = Form(1.0),
    x: float = Form(0.0),
    y: float = Form(0.0),
    z: float = Form(0.5)
):
    # Validate file type
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image.")

    # Save uploaded file
    file_extension = os.path.splitext(file.filename)[1]
    temp_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, temp_filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        # Execute the pipeline script
        # Using sys.executable to ensure we use the same python environment
        import sys
        process = subprocess.run(
            [sys.executable, "run_infer.py", file_path, str(dimension), str(x), str(y), str(z)],
            capture_output=True,
            text=True,
            check=True
        )
        return {"status": "success", "message": f"Model ({dimension}m) spawned in Gazebo!", "output": process.stdout}
    except subprocess.CalledProcessError as e:
        return {"status": "error", "message": "Pipeline execution failed.", "error": e.stderr}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# Serve static files
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
