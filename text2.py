import bpy
import sys
import os
import random

# =========================
# USER RANDOMIZATION KNOBS
# =========================
RANDOMIZE = True
HUE_SHIFT = 0.03
SAT_JITTER = 0.25
VAL_JITTER = 0.3
ROUGHNESS_JITTER = 0.35
METALLIC_JITTER = 0.2

ADD_DIRT = True
DIRT_STRENGTH = 0.30
DIRT_SCALE = 18.0

ADD_BUMP = True
BUMP_STRENGTH = 0.2
BUMP_SCALE = 40.0

TEXTURE_RES = 2048
COLLISION_DECIMATE = 0.1

def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))

argv = sys.argv
argv = argv[argv.index("--") + 1:]
input_path = argv[0]
output_dir = argv[1]
# Get index and timestamp for uniqueness
obj_index = argv[2] if len(argv) > 2 else "0"
timestamp = argv[3] if len(argv) > 3 else "0"

os.makedirs(output_dir, exist_ok=True)

# --------- CLEAN SCENE ----------
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# --------- IMPORT GLB ----------
bpy.ops.import_scene.gltf(filepath=input_path)
mesh_objs = [o for o in bpy.context.selected_objects if o.type == 'MESH']
if not mesh_objs:
    print("Error: No mesh found.")
    sys.exit(1)

obj = mesh_objs[0]
bpy.context.view_layer.objects.active = obj
obj.select_set(True)

# --------- APPLY TRANSFORMS & NORMALIZE ----------
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bbox = obj.dimensions
scale_factor = 1.0 / max(bbox)
obj.scale = (scale_factor, scale_factor, scale_factor)
bpy.ops.object.transform_apply(scale=True)

# --------- MESH CLEANUP & UV ----------
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.remove_doubles()
bpy.ops.mesh.normals_make_consistent(inside=False)

if not obj.data.uv_layers:
    print("No UVs found, generating smart UV project...")
    bpy.ops.uv.smart_project()
else:
    print(f"Using existing UVs: {[uv.name for uv in obj.data.uv_layers]}")

bpy.ops.object.mode_set(mode='OBJECT')

# --------- CREATE BAKE IMAGE ----------
bake_img = bpy.data.images.new(f"Bake_{timestamp}", width=TEXTURE_RES, height=TEXTURE_RES)

# --------- MATERIAL RANDOMIZATION ----------
def randomize_material(mat):
    if mat is None: return
    mat.use_nodes = True
    nt = mat.node_tree
    nodes = nt.nodes
    links = nt.links

    bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf is None: return

    img_node = nodes.new(type='ShaderNodeTexImage')
    img_node.image = bake_img
    nodes.active = img_node

    if not RANDOMIZE: return

    # Roughness/Metallic
    if "Roughness" in bsdf.inputs:
        bsdf.inputs["Roughness"].default_value = clamp(bsdf.inputs["Roughness"].default_value + random.uniform(-ROUGHNESS_JITTER, ROUGHNESS_JITTER))
    if "Metallic" in bsdf.inputs:
        bsdf.inputs["Metallic"].default_value = clamp(bsdf.inputs["Metallic"].default_value + random.uniform(-METALLIC_JITTER, METALLIC_JITTER))

    # Base Color
    base_input = bsdf.inputs["Base Color"]
    hsv = nodes.new(type='ShaderNodeHueSaturation')
    hsv.inputs["Hue"].default_value = 0.5 + random.uniform(-HUE_SHIFT, HUE_SHIFT)
    hsv.inputs["Saturation"].default_value = 1.0 + random.uniform(-SAT_JITTER, SAT_JITTER)
    hsv.inputs["Value"].default_value = 1.0 + random.uniform(-VAL_JITTER, VAL_JITTER)

    if base_input.is_linked:
        src = base_input.links[0].from_socket
        links.remove(base_input.links[0])
        links.new(src, hsv.inputs["Color"])
    else:
        hsv.inputs["Color"].default_value = base_input.default_value
    links.new(hsv.outputs["Color"], base_input)

    # Dirt
    if ADD_DIRT:
        texcoord = nodes.new(type='ShaderNodeTexCoord')
        mapping = nodes.new(type='ShaderNodeMapping')
        noise = nodes.new(type='ShaderNodeTexNoise')
        ramp = nodes.new(type='ShaderNodeValToRGB')
        mix = nodes.new(type='ShaderNodeMixRGB')
        mapping.inputs["Scale"].default_value = (DIRT_SCALE, DIRT_SCALE, DIRT_SCALE)
        ramp.color_ramp.elements[0].position = 0.35
        mix.blend_type = 'MULTIPLY'; mix.inputs["Fac"].default_value = DIRT_STRENGTH
        links.new(texcoord.outputs["Object"], mapping.inputs["Vector"])
        links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
        links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        src = base_input.links[0].from_socket; links.remove(base_input.links[0])
        links.new(src, mix.inputs[1]); links.new(ramp.outputs["Color"], mix.inputs[2])
        links.new(mix.outputs["Color"], base_input)

for mat in obj.data.materials:
    randomize_material(mat)

# --------- BAKE ----------
bpy.context.scene.render.engine = 'CYCLES'
bpy.context.scene.cycles.device = 'CPU'
bpy.context.scene.render.bake.use_pass_direct = False
bpy.context.scene.render.bake.use_pass_indirect = False
bpy.context.scene.render.bake.use_pass_color = True
bpy.ops.object.select_all(action='DESELECT')
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.object.bake(type='DIFFUSE')

# --------- SAVE TEXTURE ----------
texture_filename = f"texture_{timestamp}.png"
texture_path = os.path.join(output_dir, texture_filename)
bake_img.filepath_raw = texture_path
bake_img.file_format = 'PNG'
bake_img.save()

# --------- CREATE CLEAN VISUAL MATERIAL ----------
# Enforce strict uniqueness for material name to prevent Gazebo collisions
unique_mat_name = f"Material_{obj_index}_{timestamp}"
final_mat = bpy.data.materials.new(name=unique_mat_name)
final_mat.use_nodes = True
nodes = final_mat.node_tree.nodes
links = final_mat.node_tree.links
nodes.clear()
bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
out = nodes.new(type='ShaderNodeOutputMaterial')
tex = nodes.new(type='ShaderNodeTexImage')
tex.image = bake_img
links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
obj.data.materials.clear()
obj.data.materials.append(final_mat)

# --------- EXPORT VISUAL MESH ----------
visual_path = os.path.join(output_dir, "visual.obj")
bpy.ops.wm.obj_export(filepath=visual_path, export_selected_objects=True, up_axis = 'Z', forward_axis = 'Y')

# --------- CREATE COLLISION MESH ----------
bpy.ops.object.select_all(action='DESELECT')
collision_obj = obj.copy()
collision_obj.data = obj.data.copy()
bpy.context.collection.objects.link(collision_obj)
collision_obj.data.materials.clear()
bpy.context.view_layer.objects.active = collision_obj
collision_obj.select_set(True)
mod = collision_obj.modifiers.new(name="Decimate", type='DECIMATE')
mod.ratio = COLLISION_DECIMATE
bpy.ops.object.modifier_apply(modifier="Decimate")
collision_path = os.path.join(output_dir, "collision.obj")
bpy.ops.wm.obj_export(filepath=collision_path, export_selected_objects=True)

# Output dimensions for Gazebo Stable Box Collision
print(f"---DIMENSIONS_START---")
print(f"{obj.dimensions[0]},{obj.dimensions[1]},{obj.dimensions[2]}")
print(f"---DIMENSIONS_END---")
print("Processing complete")
