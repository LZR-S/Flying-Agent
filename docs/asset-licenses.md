# Scene asset sources and terms

The repository's Apache-2.0 license applies to project-authored code. Third-party scene assets retain their original terms.

| Asset | Files | Source and terms |
| --- | --- | --- |
| Character in `facing`, `open`, and `hidden` | `webots/assets_created/Meshy_Elven_Warrior/` | Meshy-generated asset supplied by the project owner. Redistribution of this release is authorized by the owner; the original [Meshy terms](https://www.meshy.ai/terms-of-use) apply. |
| Character in `terrace` | `webots/assets_created/Ada_Wang/` | Meshy-generated asset supplied by the project owner, including the source GLB and prepared Webots meshes and textures. Redistribution of this release is authorized by the owner; the original [Meshy terms](https://www.meshy.ai/terms-of-use) apply. |
| Terrace sky and stone textures | `webots/assets_created/terrace/sky_*`, `sunny_sky_*`, `stone_*` | [Poly Haven](https://polyhaven.com/) assets under CC0-1.0. See [terrace asset notes](../webots/assets_created/terrace/README.md) and [source hashes](../webots/assets_created/terrace/sources.json). |
| Terrace ocean and olive assets | `webots/assets_created/terrace/ocean_*`, `olive_leaves_*`, `water_normal.png`, `sunny_water_normal.png` | Project-authored procedural assets. |
| Webots standard PROTO dependencies | Referenced from `webots/worlds/*.wbt` | Loaded from the fixed Webots R2025a upstream URLs. They are not copied into this repository. |

The preserved earlier terrace subject mesh, `webots/assets_created/terrace/subject.obj`, also derives from the Meshy Elven Warrior asset. `configs/assets.json` records file hashes for reproducibility.
