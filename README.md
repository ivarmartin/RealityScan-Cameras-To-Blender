# Reality Capture → Blender Camera Importer

Import camera positions and orientations from Reality Capture's **Internal/External Camera Parameters** CSV export into Blender as visual frustums, real camera objects, and textured image quads.

## What it does

The script reads an RC camera parameter CSV and creates three Blender collections:

| Collection | Contents |
|---|---|
| `{filename}_Frustums` | Pyramid meshes representing each camera's field of view. Apex at camera position, base pointing in the look direction. All share a single instanced mesh for efficiency. |
| `{filename}_Cameras` | Actual Blender camera objects with correct focal length and sensor size. Select one and press **Numpad 0** to look through it. If thumbnail images are provided, each camera also gets a background image overlay. |
| `{filename}_Images` | UV-mapped quads textured with the drone photos, positioned at each camera's look direction. Uses an unlit emission shader — visible in Material Preview mode and compatible with GLB export. |

Collection names are derived from the CSV filename (e.g. `Sanda-230621.csv` → `Sanda-230621_Frustums`), so you can batch-import multiple flights into the same Blender scene without collisions.

## Rotation math

Reality Capture uses a Z-up right-handed coordinate system (X=East, Y=North, Z=Up) with yaw/pitch/roll Euler angles. The default camera orientation (0/0/0) points straight down (-Z) with the image top facing North (+Y).

The rotation matrix is computed using RC's official `EulerRotation` formula [published by the RC development team](https://forums.unrealengine.com/t/knowledge-base-registration-export-and-camera-orientations/682588), then converted to Blender's camera convention (local -Z = look direction, local +Y = up).

Both RC and Blender are Z-up right-handed systems, so positions map directly with no axis swapping.

## Focal length handling

RC's exported `$(f)` value is the **35mm-equivalent focal length**, not the physical lens focal length. The script converts it automatically:

```
f_actual = f_35eq × sensor_width / 36.0
```

You need to set your actual sensor dimensions in the script. Common drone sensors:

| Drone | Sensor | `SENSOR_WIDTH_MM` | `SENSOR_HEIGHT_MM` |
|---|---|---|---|
| DJI Mavic 3 (Hasselblad) | 4/3-inch | 17.3 | 13.0 |
| DJI Air 2S | 1-inch | 13.2 | 8.8 |
| DJI Phantom 4 Pro | 1-inch | 13.2 | 8.8 |
| DJI Mini 3 Pro | 1/1.3-inch | 9.7 | 7.3 |

## Exporting from Reality Capture

1. Align your images in Reality Capture as usual
2. In the **WORKFLOW** tab, click **Registration → Export Registration...**
3. In the export dialog, set the format to **Internal/External Camera Parameters**
4. Set the file type to **CSV** (`.csv`)
5. Choose a save location and export

This produces a CSV with the header `#name,x,y,alt,yaw,pitch,roll,f,px,py,k1,k2,k3,k4,t1,t2`. The script uses the first 8 columns (name through focal length); distortion parameters are ignored.

## Setup

### Required

1. Export cameras from Reality Capture (see above)
2. Edit `CSV_PATH` in the script to point to your CSV file

### Optional (for image quads + camera backgrounds)

3. Create a `thumbs` folder next to your CSV
4. Export low-resolution versions of your photos (e.g. 400×300 JPG) into that folder, keeping the **exact same filenames** as the originals
5. Edit `IMAGES_FOLDER` in the script to point to the thumbs folder

If the images folder doesn't exist, the script skips image quads and camera backgrounds — frustums and cameras are still created.

## Usage

1. Open Blender
2. Switch to the **Scripting** workspace
3. Open the script (or paste it into a new text block)
4. Edit the paths and settings at the top
5. Click **Run Script**

To see image textures in the viewport, switch to **Material Preview** mode (`Z` → Material Preview).

To match the camera view frame to your photos, set your scene render resolution to the same aspect ratio as your images (e.g. 4000×3000 for 4:3) under **Properties → Output → Format**.

## Configurable parameters

```python
# Paths
CSV_PATH = r"path\to\your\export.csv"
IMAGES_FOLDER = r"path\to\your\thumbs"

# Frustum pyramids
FRUSTUM_DEPTH = 5.0        # Distance from apex to base (meters)
HALF_ANGLE_DEG = 30.0      # How wide the pyramid opens
ASPECT_W = 4               # Base aspect ratio width
ASPECT_H = 3               # Base aspect ratio height

# Image quads (independent of frustum size)
IMAGE_DEPTH = 5.0           # Distance from camera to image plane
IMAGE_HALF_ANGLE_DEG = 30.0 # How wide the image quad is

# Camera sensor (must match your drone)
SENSOR_WIDTH_MM = 17.3
SENSOR_HEIGHT_MM = 13.0

# Collection naming (auto-derived from CSV filename, or override manually)
COLLECTION_PREFIX = "MyFlight"
```

## Notes

- Frustum meshes are instanced (single mesh data block shared across all objects) for minimal memory usage
- Image quads use an Emission shader, making them visible without scene lighting and compatible with glTF/GLB export
- Camera background images are set at 70% opacity and displayed behind scene geometry
- Filename matching for images is case-insensitive
- The script prints progress every 100 cameras and warns about any missing image files
- Running the script multiple times with the same CSV will reuse existing collections (no duplicates created)

## Requirements

- Blender 3.0+ (tested with 4.x)
- No external Python dependencies — uses only `bpy`, `csv`, `math`, `os`, and `mathutils`

## License

MIT
