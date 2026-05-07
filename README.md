# 🚀 Gen2Sim: One-Click Image to Gazebo Pipeline

Welcome to **Gen2Sim**! This tool allows you to take a simple photo of an object (like a chair or a banana) and automatically turn it into a high-quality 3D model that "spawns" directly into a Gazebo robot simulation.

This guide is designed for **absolute beginners**. Follow these steps in order, and you will have the pipeline running in no time.

---

## 📋 Table of Contents
1. [What You Need (Prerequisites)](#-what-you-need-prerequisites)
2. [Step 1: Installation & Setup](#-step-1-installation--setup)
3. [Step 2: Configuring Your Credentials](#-step-2-configuring-your-credentials)
4. [Step 3: Running the Simulation](#-step-3-running-the-simulation)
5. [Step 4: Running the Pipeline](#-step-4-running-the-pipeline)
6. [Step 5: Using the Web Dashboard](#-step-5-using-the-web-dashboard)

---

## 💻 What You Need (Prerequisites)

Before starting, ensure your computer has the following:
*   **Operating System**: Linux (Ubuntu 22.04 or 24.04 is recommended).
*   **A Remote GPU Server**: This project uses a powerful remote computer to "think" (inference). You must have the IP address and password for this server.
*   **Blender**: Version 4.2 or higher.
*   **ROS 2 & Gazebo**: Specifically ROS 2 Jazzy or Humble with Gazebo Sim.

---

## 🛠 Step 1: Installation & Setup

Open your terminal (Ctrl+Alt+T) and run these commands one by one.

### 1.1 Install Python Dependencies
The pipeline needs a few Python libraries to talk to the server and manage the web interface.
```bash
pip install fastapi uvicorn paramiko
```

### 1.2 Install Blender
If you don't have Blender 4.2+, download it from [blender.org](https://www.blender.org/download/). 
*   **Note your Blender path**: You will need the exact location of the `blender` executable (e.g., `/opt/blender-4.2/blender`).

### 1.3 Install ROS 2 & Gazebo
Ensure you have ROS 2 installed. You also need the "create" tool for Gazebo:
```bash
sudo apt update
sudo apt install ros-$ROS_DISTRO-ros-gz-sim
```

---

## 🔑 Step 2: Configuring Your Credentials

You need to tell the code where your Blender is and how to talk to your GPU server.

### 2.1 Update `app.py`
1.  Open `app.py` in a text editor.
2.  Find **Line 20**: `BLENDER_PATH = "/opt/blender-4.5.4-linux-x64/blender"`
3.  Change the path inside the quotes to **your** Blender location.

### 2.2 Update `run_infer.py`
1.  Open `run_infer.py` in a text editor.
2.  Find the **CONFIG** section (Lines 8-12):
    *   `HOST`: Change to your GPU server's IP address.
    *   `USERNAME`: Your server username.
    *   `PASSWORD`: Your server password.
    *   `REMOTE_BASE`: The folder path on the server where `stable-fast-3d` is installed.

---

## 🧊 Step 3: Running the Simulation

Before starting the pipeline, Gazebo must be running so it can "receive" the objects.

1.  Open a **new terminal**.
2.  Run the following command to start an empty Gazebo world:
    ```bash
    gz sim empty.sdf
    ```
    *(Leave this terminal open!)*

---

## 🏃 Step 4: Running the Pipeline

Now, let's start the "brain" of the project.

1.  Open **another terminal** in your `Project` folder.
2.  Start the FastAPI server:
    ```bash
    python3 app.py
    ```
3.  You should see a message saying: `Uvicorn running on http://0.0.0.0:8000`.

---

## 🌐 Step 5: Using the Web Dashboard

1.  Open your web browser (Chrome or Firefox).
2.  Type `http://localhost:8000` in the address bar.
3.  **To Spawn an Object**:
    *   Click **"Choose File"** and select a photo of an object (JPG or PNG).
    *   (Optional) Adjust the **Scale** (size) or **X/Y/Z** coordinates.
    *   Click the **"Generate & Spawn"** button.
4.  **Watch the Logs**: The screen will show you real-time progress:
    *   *Phase 1*: Talking to the GPU server.
    *   *Phase 2*: Blender is cleaning the mesh and baking textures.
    *   *Phase 3*: The object is being teleported into Gazebo!

---

## 📂 File Structure (What's in this folder?)

*   `app.py`: The main controller (Master).
*   `run_infer.py`: Handles the remote GPU connection.
*   `text2.py`: The Blender script for materials and collisions.
*   `outputs/`: Where your finished 3D models are saved.
*   `uploads/`: Where your uploaded photos are kept.
*   `static/`: The files for the website you see in your browser.

---

## ⚠️ Troubleshooting

*   **"Command not found: ros2"**: Make sure you have "sourced" your ROS 2 environment: `source /opt/ros/jazzy/setup.bash`.
*   **Inference Failed**: Check your internet connection and ensure your GPU server is turned on.
*   **Blender Error**: Double-check the `BLENDER_PATH` in `app.py`. It must point to the actual file named `blender`, not just the folder.

---
**Happy Simulating!** 🤖🍌🪑
