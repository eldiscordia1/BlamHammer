# Halo CE MCC pipeline

Research checked 2026-10-24. Installed Steam app 1532190, build 11722677.
`tool.exe` was executed locally and its command help confirmed the arguments below.

## Source and tag formats

JMS 8200 is a text stream. In order: version, node checksum, node count;
each node has a name, child/sibling indices, XYZW quaternion and XYZ translation;
material count and name/bitmap-path pairs; marker count and marker records;
region count and names; vertex count; triangle count. A vertex contains node0,
XYZ position, XYZ normal, node1, node1 weight, UVW. A triangle contains region,
material and three zero-based vertex indices. The exporter writes one identity
`frame` node, checksum 0, no model markers, one `unnamed` region, flat normals,
node0=0, node1=-1, weight=0, W=0. Scenario spawns are not JMS model markers.
Editor coordinates are Z-up JMS units: 100 units = one Halo world unit.

Sources: [working exporter implementation](https://github.com/General-101/Halo-Asset-Blender-Development-Toolset/blob/master/io_scene_halo/file_jms/build_asset.py),
[original Halo 1 exporter](https://github.com/HaloMods/HaloContentToolScripts/blob/master/Halo1/JMS_Exporter_v1-0-4.ms).

## Geometry and materials

World surfaces must form a sealed mesh, with normals into playable space.
BlamHammer represents rooms as free-space volumes and solid brushes as obstacles.
It unions rooms, subtracts obstacles, then reverses the resulting boundary for
Halo. This removes internal faces and intersections; it is not a GoldSrc MAP export.
Face provenance preserves shader assignments through booleans. UV coordinates are
projected onto a non-degenerate face basis, with scale, offset and rotation.
Shader tag paths are stored in the project; JMS uses the shader basename which
Tool resolves beneath tags. Duplicate names are exported as deterministic short
aliases, with byte-for-byte copies of the selected tags in `tags/blamhammer/shaders`.
Copies refresh when source tags change; replaced copies receive `.blamhammer.bak`
backups. Original tags and project assignments remain unchanged. Both Export JMS
and Build BSP use this same resolver. Generated aliases stay out of the browser.
When transferring a JMS to another installation, include the generated shader
copies and their referenced assets, or rebuild from the project there.
`+sky` is a special Halo surface, not a fabricated texture.

Sources: [level creation, independently reproducible guide](https://c20.reclaimers.net/h1/guides/levels/box-level/),
[Manifold provenance](https://github.com/elalish/manifold/wiki/Manifold-Library).
Shader name matching: [H1 material naming research](https://www.reclaimers.net/h1/source-data/h1-materials/).

## Commands, working directory = HCEEK root

For a project named `blamhammer_demo`, source goes to
`data/levels/blamhammer/blamhammer_demo/models/blamhammer_demo.jms`.

```text
tool.exe structure levels\blamhammer\blamhammer_demo blamhammer_demo
tool.exe lightmaps levels\blamhammer\blamhammer_demo\blamhammer_demo blamhammer_demo 0 0.3
tool.exe build-cache-file levels\blamhammer\blamhammer_demo\blamhammer_demo classic none
sapien.exe <absolute path to scenario tag>
guerilla.exe <absolute path to scenario tag>
```

Structure produces `.scenario_structure_bsp` and, on the first import, a
`.scenario` referencing it. Existing scenarios must be preserved when rebuilding.
Guerilla edits tag fields, scenario type and skies. Sapien places scenario objects
and spawns. Tool imports geometry, bakes lighting and packages the tag graph into
`maps/blamhammer_demo.map`. A cache build is not proof of in-game playability.
There is no separate H1 `compile-scenario` verb; the editor's Compile Scenario
action prepares the BSP/scenario and writes supported placements, sky and scenario
type through Reclaimer's tag definitions. It re-reads the serialized tag and only
updates editor-owned scenarios with a matching SHA-256 ownership record. An
externally edited scenario is left for Sapien; Build BSP and Package current
Sapien scenario preserve those placements.

Sources: [Microsoft tool overview](https://learn.microsoft.com/en-us/halo-master-chief-collection/general/overview-tools),
[H1 Tool command research](https://c20.reclaimers.net/h1/h1-ek/h1-tool/), installed Tool help.

## Assets

The installed README says to extract HCEEK.7z before editing. Extraction uses the
bundled 7zr with `-aos` to preserve existing files. No game assets are distributed
with the editor. Shader previews read local bitmap tags or original TIFFs.
Binary layouts are verified against [Invader's bitmap definition](https://github.com/SnowyMouse/invader/blob/master/src/tag/hek/definition/bitmap.json).

## Verification contract

A build requires exit code zero, nonempty expected outputs, and a newly written
BSP/MAP (a pre-existing output does not prove success). Actual stdout/stderr and
report files are retained. Tool errors stop the pipeline. The placement handoff
JSON states whether markers were synchronized or still require Sapien transfer.
Supported direct placements are player starts, multiplayer item collections,
single-player weapons, vehicles and scenery. Scenario coordinates are converted
from JMS units to world units and yaw from degrees to radians.

Subdivision uses shared edge vertices and triangle grids only on selected faces.
Unselected faces remain single polygons with shared boundary points; Manifold's
ear clipping triangulates those polygons for rendering/export without degenerate
triangles or T-junctions. Manifold performs plane clipping
and caps both outputs; source faces retain material/UV settings. Caps inherit the
first source face's settings. Export still uses the same room/solid CSG path.
The feature integration fixture was compiled with real HCEEK: 266 input triangles,
266 BSP surfaces, four shader groups, verified collision BSP, lightmaps and MAP.
See `artifacts/features_verification.json`; the compiler log for the final structure
build is `reports/blamhammer/20261024-190402-structure.log` beneath HCEEK.

Duplicate-shader regression: both installed `digsite/levels/dusk/shaders/grass`
and `digsite/levels/indoor/_dig/shaders/grass` compiled into one BSP and MAP.
The BSP render and collision shader references were re-read and matched against
the selected originals. Evidence: `artifacts/shader_names_verification.json`.

## BSP import

`bsp.py` reads version-5 Halo 1 `.scenario_structure_bsp` tags through the existing
Reclaimer definitions. The Halo Blender toolset's
[BSP importer](https://github.com/General-101/Halo-Asset-Blender-Development-Toolset/blob/master/io_scene_halo/file_tag/build_scene/build_bsp.py)
was checked for the 100× unit conversion, reversed render triangle order, flipped
V coordinates, and collision edge traversal. Both uncompressed and compressed
vertex buffers are supported. No Blender installation or new dependency is needed.

Imported meshes use the existing Brush/Face project data, with optional affine
UV mappings and surface flags. Old projects retain their defaults. Rendering,
picking, transforms, subdivision and history use the same model. Mesh validation
checks faces while allowing open render surfaces; closed solid/room validation
and CSG stay unchanged. Imported surfaces join the room/solid output at JMS export.

The render stream exports as render-only (`!`), while the original collision shell
exports as collision-only (`@`), player clips (`*`), sky, and its two-sided/ladder/
breakable flags. Two-sided collision polygons occur twice in a compiled BSP;
duplicates are removed because Tool generates the second side from `%`. These
[material symbols](https://reclaimers.net/h1/source-data/h1-materials/) let Tool
rebuild collision without treating transparent detail as an unsealed solid.

Imports add a grid-aligned, padded `+sky` room and choose an unused output folder.
They do not write their source tags or import scenario placements, portals, fog,
weather, scripts or lighting. Imported render/collision topology is retained;
geometry edits still need compiler/collision verification. CSG/clip operations
explicitly require regular brushes instead of interpreting an open mesh as a solid.

Tests cover binary parsing, both vertex layouts, units/winding/UVs, collision flags,
sky recovery/enclosure, output isolation, malformed data, serialization, subdivision
and JMS parsing. Real Qt tests cover File → Open BSP, picking, framing, UV edits,
undo/redo, save/reopen and cancellation. Real HCEEK rebuilt tutorial (984 render
triangles) and Blood Gulch (5,503), checking all source render vertices and UVs in
the compiled tags. Maximum observed coordinate drift: 0.000039 Halo units;
maximum UV drift: 0.00000024. Tutorial also produced lightmaps and a 91,332,095-byte
MAP. No imported-map gameplay test was performed.
