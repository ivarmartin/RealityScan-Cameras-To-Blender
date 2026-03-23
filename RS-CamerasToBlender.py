"""
Import Reality Capture camera positions into Blender.

Creates three collections:
  - RC_Frustums: Visual frustum pyramids (mesh) for quick overview
  - RC_Cameras:  Actual Blender camera objects with correct focal length
  - RC_Images:   Textured quads showing the drone photos, positioned at each
                 camera's look direction. Visible in Material Preview mode.

Usage:
  1. Open Blender
  2. Go to Scripting workspace
  3. Open this file or paste it
  4. Edit CSV_PATH and IMAGES_FOLDER below
  5. Put low-res JPGs (same filenames as originals) in the IMAGES_FOLDER
  6. Run the script
"""

import bpy
import csv
import math
import os
from mathutils import Matrix, Vector

# =============================================================================
# USER SETTINGS - Tweak these
# =============================================================================

CSV_PATH = r"E:\LIVE-SANDAMAPPING-3INTERMEDIATE-Maps-Models\FromRC\230621-nadir.csv"

# Frustum pyramid size: distance from apex (camera position) to the base
FRUSTUM_DEPTH = 1.0  # meters

# Aspect ratio of the base (width:height). 4:3 matching your sensor.
ASPECT_W = 4
ASPECT_H = 3

# Half-angle of the pyramid (controls how wide the base is relative to depth).
# ~30 degrees gives a natural-looking camera frustum.
HALF_ANGLE_DEG = 30.0

# Sensor dimensions in mm (for the real Blender camera objects).
# Your drone: 4/3-inch CMOS, 84° diagonal FOV, 24mm equiv.
SENSOR_WIDTH_MM = 17.3
SENSOR_HEIGHT_MM = 13.0

# RC's exported $(f) is the 35mm-equivalent focal length (relative to 36mm sensor width).
# We convert to actual focal length: f_actual = f_35eq * sensor_width / 36.0
# This is done automatically in the script below.

# Collection name prefix — derived automatically from the CSV filename.
# e.g. "Sanda-230621.csv" -> collections named "Sanda-230621_Frustums", etc.
# Override this manually if you want a custom prefix.
COLLECTION_PREFIX = os.path.splitext(os.path.basename(CSV_PATH))[0]

# Image quads: textured planes showing the drone photos.
# Place low-res JPGs (same filenames as originals) in this folder:
IMAGES_FOLDER = r"E:\LIVE-SANDAMAPPING-3INTERMEDIATE-Maps-Models\FromRC\thumbs"

# Image quad size (independent of frustum size).
# Distance from camera position to the image plane along the look direction.
IMAGE_DEPTH = 1.0  # meters
# Half-angle controlling how wide the image quad is (like HALF_ANGLE_DEG for frustums).
IMAGE_HALF_ANGLE_DEG = 30.0

# =============================================================================
# ROTATION MATH - Reality Capture conventions
# =============================================================================
#
# RC coordinate system: X=East, Y=North, Z=Up (right-handed, Z-up)
# RC default camera (yaw=0, pitch=0, roll=0) looks straight DOWN (-Z),
# with the top of the image pointing North (+Y).
#
# RC's official rotation function (from their developer forum) produces a 3x3
# matrix whose rows are the camera's local axes in world coordinates:
#   Row 0 = camera right   (image +X direction)
#   Row 1 = camera down    (image -Y direction, i.e. bottom of image)
#   Row 2 = camera optical axis (look direction)
#
# Blender camera convention: looks along local -Z, with local +Y = up.
# Blender is also Z-up right-handed, so positions map directly.
#
# To orient a Blender object so its local -Z points along the RC look direction
# and local +Y points along the RC image-up direction, we build a 3x3 matrix
# whose columns are:
#   col 0 = RC row 0          (camera right  -> Blender local X)
#   col 1 = -RC row 1         (camera up     -> Blender local Y)
#   col 2 = -RC row 2         (camera -look  -> Blender local Z)
#
# This gives us a proper rotation matrix (det = +1) that we pack into a 4x4.


def rc_rotation_matrix(yaw_deg, pitch_deg, roll_deg):
    """
    Compute the 3x3 camera rotation matrix using Reality Capture's
    official EulerRotation formula (yaw/pitch/roll in degrees).

    Returns a 3x3 list-of-lists where:
      row 0 = camera right axis in world coords
      row 1 = camera down axis in world coords
      row 2 = camera look (optical) axis in world coords
    """
    y, p, r = yaw_deg, pitch_deg, roll_deg
    cx = math.cos(math.radians(r))
    cy = math.cos(math.radians(p))
    cz = math.cos(math.radians(y))
    sx = math.sin(math.radians(r))
    sy = math.sin(math.radians(p))
    sz = math.sin(math.radians(y))

    return [
        [cx * cz + sx * sy * sz,  -cx * sz + cz * sx * sy,  -cy * sx],
        [-cy * sz,                -cy * cz,                  -sy],
        [cx * sy * sz - cz * sx,   cx * cz * sy + sx * sz,  -cx * cy],
    ]


def rc_to_blender_matrix(yaw_deg, pitch_deg, roll_deg, x, y, z):
    """
    Build a 4x4 Blender world matrix from RC camera parameters.
    """
    R = rc_rotation_matrix(yaw_deg, pitch_deg, roll_deg)

    # Blender columns from RC rows (see convention notes above)
    cam_right = Vector(R[0])           # col 0
    cam_up = Vector([-R[1][0], -R[1][1], -R[1][2]])  # col 1 = -row1
    cam_back = Vector([-R[2][0], -R[2][1], -R[2][2]])  # col 2 = -row2

    mat = Matrix((
        (cam_right.x, cam_up.x, cam_back.x, x),
        (cam_right.y, cam_up.y, cam_back.y, y),
        (cam_right.z, cam_up.z, cam_back.z, z),
        (0, 0, 0, 1),
    ))
    return mat


# =============================================================================
# FRUSTUM MESH CREATION
# =============================================================================

def create_frustum_mesh(name, depth, aspect_w, aspect_h, half_angle_deg):
    """
    Create a pyramid mesh object representing a camera frustum.

    The apex is at the origin (camera position).
    The base extends along -Z (the Blender camera look direction),
    at distance `depth` from the apex.

    Returns the created Blender object (not yet linked to any collection).
    """
    half_angle = math.radians(half_angle_deg)
    base_half_h = depth * math.tan(half_angle)
    # Scale width so that w/h = aspect_w/aspect_h
    base_half_w = base_half_h * (aspect_w / aspect_h)

    # Apex at origin
    apex = Vector((0, 0, 0))

    # Base corners at -Z (look direction in Blender camera space)
    # Order: top-left, top-right, bottom-right, bottom-left (when looking from behind the camera)
    base_tl = Vector((-base_half_w,  base_half_h, -depth))
    base_tr = Vector(( base_half_w,  base_half_h, -depth))
    base_br = Vector(( base_half_w, -base_half_h, -depth))
    base_bl = Vector((-base_half_w, -base_half_h, -depth))

    verts = [apex, base_tl, base_tr, base_br, base_bl]

    faces = [
        (0, 1, 2),  # top triangle
        (0, 2, 3),  # right triangle
        (0, 3, 4),  # bottom triangle
        (0, 4, 1),  # left triangle
        (1, 4, 3, 2),  # base quad (the "image frame")
    ]

    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()

    obj = bpy.data.objects.new(name, mesh)
    return obj


# =============================================================================
# IMAGE QUAD CREATION
# =============================================================================

def create_image_quad_mesh(name, depth, aspect_w, aspect_h, half_angle_deg):
    """
    Create a single quad (plane) positioned along -Z at the given depth,
    sized to match the aspect ratio — like the frustum base, but just the quad.
    Includes UV coordinates for texturing.

    Returns a Blender mesh (not an object — each image quad needs its own
    object+material, so we create fresh mesh copies per camera).
    """
    half_angle = math.radians(half_angle_deg)
    base_half_h = depth * math.tan(half_angle)
    base_half_w = base_half_h * (aspect_w / aspect_h)

    # Quad corners at -Z, viewed from behind the camera (looking in -Z direction):
    #   TL --- TR
    #   |       |
    #   BL --- BR
    verts = [
        Vector((-base_half_w,  base_half_h, -depth)),  # 0: top-left
        Vector(( base_half_w,  base_half_h, -depth)),  # 1: top-right
        Vector(( base_half_w, -base_half_h, -depth)),  # 2: bottom-right
        Vector((-base_half_w, -base_half_h, -depth)),  # 3: bottom-left
    ]
    faces = [(0, 3, 2, 1)]  # winding so normal faces back toward camera (+Z)

    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()

    # Add UV layer — map quad corners to full image [0,0]-[1,1]
    uv_layer = mesh.uv_layers.new(name="UVMap")
    # from_pydata creates loops in face vertex order: 0, 3, 2, 1
    # We need: TL=(0,1), BL=(0,0), BR=(1,0), TR=(1,1)
    uv_layer.data[0].uv = (0.0, 1.0)  # vert 0 = TL
    uv_layer.data[1].uv = (0.0, 0.0)  # vert 3 = BL
    uv_layer.data[2].uv = (1.0, 0.0)  # vert 2 = BR
    uv_layer.data[3].uv = (1.0, 1.0)  # vert 1 = TR

    return mesh


def create_image_material(img, mat_name):
    """
    Create a material with the image as an Emission shader (unlit, always visible).
    Also works for GLB export via glTF emissive channel.

    Args:
        img: A bpy.types.Image data block (already loaded).
        mat_name: Name for the new material.
    """
    mat = bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # Clear default nodes
    nodes.clear()

    # Emission shader (unlit — image always visible regardless of lighting)
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    tex = nodes.new("ShaderNodeTexImage")

    tex.image = img

    links.new(tex.outputs["Color"], emission.inputs["Color"])
    emission.inputs["Strength"].default_value = 1.0
    links.new(emission.outputs["Emission"], output.inputs["Surface"])

    return mat

def get_or_create_collection(name):
    """Get existing collection by name, or create and link a new one."""
    if name in bpy.data.collections:
        return bpy.data.collections[name]
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col

def main():
    # Validate CSV path
    if not os.path.isfile(CSV_PATH):
        raise FileNotFoundError(
            f"CSV not found: {CSV_PATH}\n"
            f"Edit CSV_PATH at the top of this script."
        )

    col_name_frustums = f"{COLLECTION_PREFIX}_Frustums"
    col_name_cameras = f"{COLLECTION_PREFIX}_Cameras"
    col_name_images = f"{COLLECTION_PREFIX}_Images"

    col_frustums = get_or_create_collection(col_name_frustums)
    col_cameras = get_or_create_collection(col_name_cameras)
    col_images = get_or_create_collection(col_name_images)

    # Check if images folder exists
    has_images = os.path.isdir(IMAGES_FOLDER)
    if has_images:
        print(f"Images folder found: {IMAGES_FOLDER}")
        # Build a case-insensitive lookup: lowercase name -> actual filename
        image_lookup = {}
        for fname in os.listdir(IMAGES_FOLDER):
            image_lookup[fname.lower()] = fname
    else:
        print(f"WARNING: Images folder not found: {IMAGES_FOLDER}")
        print("  Skipping image quads. Create the folder and re-run to add them.")
        image_lookup = {}

    # Read CSV
    cameras = []
    with open(CSV_PATH, "r", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            # Skip header / comment lines
            if not row or row[0].startswith("#"):
                continue
            name = row[0]
            x = float(row[1])
            y = float(row[2])
            alt = float(row[3])
            yaw = float(row[4])
            pitch = float(row[5])
            roll = float(row[6])
            focal_mm = float(row[7])
            cameras.append((name, x, y, alt, yaw, pitch, roll, focal_mm))

    print(f"Loaded {len(cameras)} cameras from CSV.")

    # --- Frustum meshes (instanced) ---
    template_obj = create_frustum_mesh(
        "_frustum_template", FRUSTUM_DEPTH, ASPECT_W, ASPECT_H, HALF_ANGLE_DEG
    )
    template_mesh = template_obj.data

    # --- Shared camera data (all share the same lens if focal length is constant) ---
    focal_lengths = set(c[7] for c in cameras)
    shared_cam_data = None
    if len(focal_lengths) == 1:
        f_35eq = cameras[0][7]
        f_actual = f_35eq * SENSOR_WIDTH_MM / 36.0
        shared_cam_data = bpy.data.cameras.new("RC_Lens")
        shared_cam_data.type = 'PERSP'
        shared_cam_data.lens = f_actual
        shared_cam_data.sensor_fit = 'HORIZONTAL'
        shared_cam_data.sensor_width = SENSOR_WIDTH_MM
        shared_cam_data.sensor_height = SENSOR_HEIGHT_MM
        shared_cam_data.display_size = 0.5
        print(f"All cameras share focal length: {f_35eq:.2f}mm (35mm equiv) -> {f_actual:.2f}mm (actual)")

    images_found = 0
    images_missing = 0

    for i, (name, x, y, alt, yaw, pitch, roll, focal_mm) in enumerate(cameras):
        obj_name = os.path.splitext(name)[0]
        world_mat = rc_to_blender_matrix(yaw, pitch, roll, x, y, alt)

        # Frustum mesh
        frustum = bpy.data.objects.new(obj_name, template_mesh)
        frustum.matrix_world = world_mat
        col_frustums.objects.link(frustum)

        # Real Blender camera
        # Background images are per camera data block, so each camera needs its own
        # data block if we're assigning images. Otherwise share for efficiency.
        actual_fname = image_lookup.get(name.lower()) if has_images else None

        if shared_cam_data and not actual_fname:
            cam_data = shared_cam_data
        else:
            if shared_cam_data:
                # Same lens params as shared, but unique data block for background image
                f_actual = shared_cam_data.lens
            else:
                f_actual = focal_mm * SENSOR_WIDTH_MM / 36.0
            cam_data = bpy.data.cameras.new(obj_name + "_lens")
            cam_data.type = 'PERSP'
            cam_data.lens = f_actual
            cam_data.sensor_fit = 'HORIZONTAL'
            cam_data.sensor_width = SENSOR_WIDTH_MM
            cam_data.sensor_height = SENSOR_HEIGHT_MM
            cam_data.display_size = 0.5

        cam_obj = bpy.data.objects.new(obj_name + "_cam", cam_data)
        cam_obj.matrix_world = world_mat
        col_cameras.objects.link(cam_obj)

        # Image quad (textured plane) + camera background image
        if actual_fname:
            img_path = os.path.join(IMAGES_FOLDER, actual_fname)

            # Load image once, reuse for both quad and background
            img = bpy.data.images.load(img_path)

            # Camera background image (visible when looking through camera)
            cam_data.show_background_images = True
            bg = cam_data.background_images.new()
            bg.image = img
            bg.alpha = 0.7
            bg.display_depth = 'BACK'

            # Textured quad
            quad_mesh = create_image_quad_mesh(
                obj_name + "_img",
                IMAGE_DEPTH, ASPECT_W, ASPECT_H, IMAGE_HALF_ANGLE_DEG
            )
            quad_obj = bpy.data.objects.new(obj_name + "_img", quad_mesh)
            quad_obj.matrix_world = world_mat

            mat = create_image_material(img, obj_name + "_mat")
            quad_obj.data.materials.append(mat)

            col_images.objects.link(quad_obj)
            images_found += 1
        elif has_images:
            images_missing += 1

        if (i + 1) % 100 == 0:
            print(f"  Created {i + 1}/{len(cameras)}...")

    # Clean up template object (mesh data persists via instancing)
    bpy.data.objects.remove(template_obj, do_unlink=True)

    print(f"\nDone.")
    print(f"  {len(cameras)} frustums in '{col_name_frustums}'")
    print(f"  {len(cameras)} cameras in '{col_name_cameras}'")
    if has_images:
        print(f"  {images_found} image quads in '{col_name_images}'")
        if images_missing:
            print(f"  WARNING: {images_missing} images not found in {IMAGES_FOLDER}")


if __name__ == "__main__":
    main()
