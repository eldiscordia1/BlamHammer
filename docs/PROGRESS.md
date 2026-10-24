# Implementation checklist

1. [x] Research JMS and actual H1A Tool commands; locate installed HCEEK.
2. [x] Implement model, solid geometry, validated project IO and JMS export.
3. [x] Implement native desktop editing, materials and owned-scenario synchronization.
4. [x] Verify save/reload, geometry, UI and real BSP/MAP compilation.
5. [x] Add shared-vertex subdivision and left/right/both clipping; verify editing,
       snapping, undo/redo, material mapping, JMS, BSP, lightmaps and MAP.

Scope reaches geometry, persistence, materials, rendering, commands, tests,
example project, launchers and documentation. The workspace was initially empty.
Existing Halo assets and scenarios must not be overwritten without backups.

Architecture: Python + native Qt widgets/OpenGL, numpy arrays, Manifold C++
boolean kernel. Small modules share one project model; history snapshots provide
atomic undo. No browser or web server. Python makes integration testable while
the expensive geometry operations and rendering execute in native libraries.

2026-10-24: 17 unit tests passed. Qt/OpenGL smoke test exercised real mouse-driven
subdivision, vertex dragging between views, three clip modes, undo/redo and save/reload.
HCEEK 2023.07.17.176677.1-QFE1 compiled the terrain/clip example: 290 triangles,
four shader groups, collision BSP verified, no degenerate-triangle warnings.
MAP: 88,793,330 bytes. Evidence: artifacts/features_verification.json and
artifacts/features_editor.png. See README for limitations and reproduction commands.

The local halo_tag_test runtime loaded the feature scenario and showed a spawned
player, HUD, weapon and textured terrain. Screenshot:
artifacts/blamhammer_features_in_game.png. This was a load/render smoke check;
extended traversal and multiplayer sessions were not tested.

Duplicate shader fix: 19 unit tests passed. Real HCEEK compiled both installed
grass shaders into one BSP/MAP; render and collision references were independently
re-read and verified. Exact source bytes and project assignments remained unchanged.
Evidence: artifacts/shader_names_verification.json. No in-game retest for this fix.

Face selection/camera controls: Ctrl-click selects/toggles multiple faces across
brushes, with scoped materials, UVs, triangulation and subdivision. WASD moves the
focused 3D view; right drag rotates in place. Real Qt mouse/keyboard tests cover
selection, undo/redo, camera directions, key-up, focus loss, text entry and Ctrl+A.
Both UI smoke scripts and all 19 unit tests passed. No HCEEK rerun for UI controls.

Project settings now save on OK using the existing validated, atomic project save.
The launcher remembers the last saved/opened project. The settings UI test verified
all fields after reload, backups, cancellation, invalid values, disk errors, first
save, remembered startup and fallback when the remembered file is missing.

Selected-face subdivision now leaves unselected faces as single polygons, adding
only shared boundary points. Rendering and export triangulate those polygons with
Manifold; the editor wireframe shows actual face boundaries. Regression checks
cover unchanged neighbors, repeated subdivision, stitched triangles, triangulation,
snapped terrain edits and undo/redo. All 19 unit tests and both UI smoke scripts
passed. HCEEK rebuilt the feature fixture: 266 triangles, four shader groups,
verified collision BSP, lightmaps and an 88,788,394-byte MAP. No in-game retest.

BSP import: File → Open BSP reads Halo CE/HCEEK tags using Reclaimer, converts
units once, preserves shader/UV and collision data, frames the map and adds a
padded +sky room. Builds target an unused import directory; source tags are
unchanged. Imported meshes retain face/vertex editing, subdivision and history;
CSG/clip remain solid-brush operations. All 24 unit tests and the existing editing
UI smoke test passed. The BSP UI test covered Blood Gulch rendering, face selection,
UVs, save/reopen, undo/redo and rejected/cancelled imports. HCEEK rebuilt tutorial
and Blood Gulch with matching render counts and verified UVs; tutorial passed
lightmaps and MAP packaging. Evidence: artifacts/bsp_import_verification.json.
Scenario objects/scripts and other BSP metadata are outside the geometry import;
no in-game playtest was performed.

Production-map camera freeze: profiling Infinity (43,259 editor faces) traced the
stall on entering the view to per-triangle picking and an unnecessary geometry
rebuild after selection. Picking now uses the cached triangles and a vectorized
ray test; selection updates colors/outlines independently of the geometry cache.
Selection no longer serializes the whole project to update its unchanged title.
Orthographic views also reuse projected vertex positions within each paint.
The profiled pick fell from 3,904 ms to about 21 ms, with no geometry/batch rebuilds
while selecting, using WASD or right-dragging. Blood Gulch measured about 5 ms.
Cache regression tests cover UV/vertex edits, CSG, selection colors, hidden
collision faces, backfaces, closest hits and marker picking. Existing navigation
tests passed. Profiling results: artifacts/camera_profile_{map}.json and .txt.
These are CPU/UI timings under profiling, not a GPU FPS guarantee. No compiler
or in-game rerun was needed for this viewport-only change.
