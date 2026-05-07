import argparse
import os
import random
from contextlib import nullcontext

import numpy as np
import rembg
import torch
import trimesh
from PIL import Image
from tqdm import tqdm

from sf3d.system import SF3D
from sf3d.utils import get_device, remove_background, resize_foreground


# =========================================================
# GEOMETRY RANDOMIZATION KNOBS
# (Physical / dimensional variation inside canonical bounds)
# =========================================================
GEOM_RANDOMIZE = True

# Non-uniform dimension scaling
X_SCALE_JITTER = 0.0009   # width variation
Y_SCALE_JITTER = 0.0009   # depth variation
Z_SCALE_JITTER = 0.0011   # height variation

# Shape profile variation
TAPER_STRENGTH = 0.25   # top vs bottom thickness variation
BEND_STRENGTH = 0.3  # mild smooth bend
BEND_AXIS = "x"         # bend along x or y

# Keep output in canonical range after perturbation
RENORMALIZE = True


# =========================================================
# GEOMETRY RANDOMIZER
# =========================================================
def randomize_geometry(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """
    Apply physically meaningful geometric variation while preserving
    object identity and keeping output in normalized canonical scale.
    """
    if not GEOM_RANDOMIZE:
        return mesh

    mesh = mesh.copy()
    v = mesh.vertices.copy()

    if len(v) == 0:
        return mesh

    # -----------------------------------------
    # Center mesh around origin
    # -----------------------------------------
    center = v.mean(axis=0)
    v = v - center

    # -----------------------------------------
    # Non-uniform XYZ scaling
    # Preserves identity but changes proportions
    # -----------------------------------------
    sx = random.uniform(1.0 - X_SCALE_JITTER, 1.0 + X_SCALE_JITTER)
    sy = random.uniform(1.0 - Y_SCALE_JITTER, 1.0 + Y_SCALE_JITTER)
    sz = random.uniform(1.0 - Z_SCALE_JITTER, 1.0 + Z_SCALE_JITTER)
    v[:, 0] *= sx
    v[:, 1] *= sy
    v[:, 2] *= sz

    # -----------------------------------------
    # Taper deformation
    # Top and bottom scale slightly differently
    # Useful for mugs, bottles, tools, etc.
    # -----------------------------------------
    z_min = v[:, 2].min()
    z_max = v[:, 2].max()
    z_span = max(z_max - z_min, 1e-8)

    z_norm = (v[:, 2] - z_min) / z_span  # [0, 1]
    taper = 1.0 + (z_norm - 0.5) * random.uniform(-TAPER_STRENGTH, TAPER_STRENGTH)

    v[:, 0] *= taper
    v[:, 1] *= taper

    # -----------------------------------------
    # Smooth bend deformation
    # Mild low-frequency warp
    # -----------------------------------------
    bend_amt = random.uniform(-BEND_STRENGTH, BEND_STRENGTH)
    if BEND_AXIS == "x":
        v[:, 0] += bend_amt * ((z_norm - 0.5) ** 2 - 0.08)
    elif BEND_AXIS == "y":
        v[:, 1] += bend_amt * ((z_norm - 0.5) ** 2 - 0.08)


    # -----------------------------------------
    # Re-normalize into canonical bounds
    # Keeps object in stable scale range
    # -----------------------------------------
    if RENORMALIZE:
        mins = v.min(axis=0)
        maxs = v.max(axis=0)
        extents = maxs - mins
        max_extent = max(extents.max(), 1e-8)
        v /= max_extent

    mesh.vertices = v
    mesh.remove_duplicate_faces()
    mesh.remove_unreferenced_vertices()
    mesh.remove_degenerate_faces()

    return mesh


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "image", type=str, nargs="+", help="Path to input image(s) or folder."
    )
    parser.add_argument(
        "--device",
        default=get_device(),
        type=str,
        help=f"Device to use. If no CUDA/MPS-compatible device is found, the baking will fail. Default: '{get_device()}'",
    )
    parser.add_argument(
        "--pretrained-model",
        default="stabilityai/stable-fast-3d",
        type=str,
        help="Path to the pretrained model. Could be either a huggingface model id or a local path. Default: 'stabilityai/stable-fast-3d'",
    )
    parser.add_argument(
        "--foreground-ratio",
        default=0.85,
        type=float,
        help="Ratio of the foreground size to the image size. Default: 0.85",
    )
    parser.add_argument(
        "--output-dir",
        default="output/",
        type=str,
        help="Output directory to save the results. Default: 'output/'",
    )
    parser.add_argument(
        "--texture-resolution",
        default=1024,
        type=int,
        help="Texture atlas resolution. Default: 1024",
    )
    parser.add_argument(
        "--remesh_option",
        choices=["none", "triangle", "quad"],
        default="none",
        help="Remeshing option",
    )
    parser.add_argument(
        "--target_vertex_count",
        type=int,
        help="Target vertex count. -1 does not perform reduction.",
        default=-1,
    )
    parser.add_argument(
        "--batch_size", default=1, type=int, help="Batch size for inference"
    )
    args = parser.parse_args()

    # Ensure args.device contains valid backend
    devices = ["cuda", "mps", "cpu"]
    if not any(args.device in device for device in devices):
        raise ValueError("Invalid device. Use cuda, mps or cpu")

    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)

    device = args.device
    if not (torch.cuda.is_available() or torch.backends.mps.is_available()):
        device = "cpu"

    print("Device used:", device)

    model = SF3D.from_pretrained(
        args.pretrained_model,
        config_name="config.yaml",
        weight_name="model.safetensors",
    )
    model.to(device)
    model.eval()

    rembg_session = rembg.new_session()
    images = []
    idx = 0

    for image_path in args.image:

        def handle_image(image_path, idx):
            image = remove_background(
                Image.open(image_path).convert("RGBA"), rembg_session
            )
            image = resize_foreground(image, args.foreground_ratio)
            os.makedirs(os.path.join(output_dir, str(idx)), exist_ok=True)
            image.save(os.path.join(output_dir, str(idx), "input.png"))
            images.append(image)

        if os.path.isdir(image_path):
            image_paths = [
                os.path.join(image_path, f)
                for f in os.listdir(image_path)
                if f.endswith((".png", ".jpg", ".jpeg"))
            ]
            for image_path in image_paths:
                handle_image(image_path, idx)
                idx += 1
        else:
            handle_image(image_path, idx)
            idx += 1

    for i in tqdm(range(0, len(images), args.batch_size)):
        image = images[i : i + args.batch_size]

        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()

        with torch.no_grad():
            with torch.autocast(
                device_type=device, dtype=torch.bfloat16
            ) if "cuda" in device else nullcontext():
                mesh, glob_dict = model.run_image(
                    image,
                    bake_resolution=args.texture_resolution,
                    remesh=args.remesh_option,
                    vertex_count=args.target_vertex_count,
                )

        if torch.cuda.is_available():
            print("Peak Memory:", torch.cuda.max_memory_allocated() / 1024 / 1024, "MB")
        elif torch.backends.mps.is_available():
            print("Peak Memory:", torch.mps.driver_allocated_memory() / 1024 / 1024, "MB")

        # -------------------------------------------------
        # Apply geometric randomization before export
        # -------------------------------------------------
        if len(image) == 1:
            mesh = randomize_geometry(mesh)
            out_mesh_path = os.path.join(output_dir, str(i), "mesh.glb")
            mesh.export(out_mesh_path, include_normals=True)
        else:
            for j in range(len(mesh)):
                mesh[j] = randomize_geometry(mesh[j])
                out_mesh_path = os.path.join(output_dir, str(i + j), "mesh.glb")
                mesh[j].export(out_mesh_path, include_normals=True)
