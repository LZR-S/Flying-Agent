# Coastal Terrace assets

This directory contains the scene's locally packaged assets. No image-generation
API, credentials or runtime texture download is required. Webots still resolves
the standard R2025a Mavic PROTO and its dependencies in the usual way.

## Sources and processing

- **Autumn Field (Pure Sky) HDRI**, Poly Haven, CC0: <https://polyhaven.com/a/autumn_field_puresky>.
  The 4K source is oriented to the scene's 29-degree warm sun, with calibrated Webots ENU
  cube faces. `sunny_sky_*.jpg` use a blue-sky display grade; `sunny_sky_*.hdr` retain
  the source colors and cap the solar hotspot before downsampling to avoid reflection
  aliasing. `weather.json` records the conversion and source hash. This is distant
  scenery, not measurable geometry. The previous Fish Hoek Beach `sky_*` assets remain
  available for reproducing historical overcast-scene experiments.
- **Concrete Floor 02**, Poly Haven, CC0: <https://polyhaven.com/a/concrete_floor_02>.
  Original 1K diffuse, roughness and OpenGL normal maps are included. `stone_warm.jpg`
  is a desaturated, lightened derivative used for the warm stone paving.
- **Olive leaves and ocean maps** are deterministic project-authored assets.
  `ocean_normal.png`, `ocean_color.png` and `ocean_roughness.png` are 2K periodic
  textures derived from three bands of a seeded wave spectrum. They add fine surface
  reflections and subtle water-color variation; mipmapping softens distant ripples.
  The water remains static scenery, with no wave animation or fluid simulation.
  The earlier `water_normal.png` and `sunny_water_normal.png` remain available for
  historical comparisons.
- The active **Ada Wang subject** comes from the user-provided Meshy GLB in
  `../Ada_Wang/`. Its `webots/` subdirectory contains the prepared 1.70 m character,
  199,999 triangles split into 12 shadow-compatible meshes, 4K base-color / normal maps,
  and 2K roughness / metalness maps.
  `../Ada_Wang/webots/manifest.json` records the source hash and resulting geometry.
  Original Meshy usage terms apply; the character is not a Poly Haven CC0 asset.
  `subject.obj` is the previous 1.75 m Elven Warrior preview mesh, retained as an
  unused reference; the terrace now uses Ada Wang.

`sources.json` records original source URLs and SHA-256 hashes. Rebuild with
`.venv/bin/python scripts/build_terrace_assets.py` from the project root. Rebuilding
requires internet access and Blender at `/Applications/Blender.app` on this Mac;
opening the scene does not require Blender. Downloaded source HDR files are kept
under the ignored `runs/webots/terrace-asset-build/` directory.

The cubemap conversion follows Webots' image-tool convention. The panorama is
rotated 0.4 turns to place the bay behind the subject. The scene geometry and
camera calibration use metres.
