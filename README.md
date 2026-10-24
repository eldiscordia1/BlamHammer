# BlamHammer!

**A Hammer-inspired 3D level editor for Halo: Combat Evolved (MCC).**

![Status](https://img.shields.io/badge/Status-Alpha-orange)
![Platform](https://img.shields.io/badge/Platform-Windows-blue)
![Source](https://img.shields.io/badge/Source-Closed--Source-red)
![Game](https://img.shields.io/badge/Game-Halo%20CE%20MCC-green)

## About

**BlamHammer! (BHammer)** is a standalone 3D level editor inspired by Valve's Hammer Editor and J.A.C.K., designed specifically for creating custom maps for **Halo: Combat Evolved in The Master Chief Collection**.

The goal is to simplify Halo CE map creation through an intuitive brush-based workflow, reducing the need to rely on external modeling software such as Blender.

BlamHammer! integrates with the official Halo CE Editing Kit (HCEEK), allowing users to create geometry, apply materials, export JMS files, compile scenarios, and test maps in Halo CE.

## Screenshots

### Editor Interface

[![BlamHammer Editor](screenshots/editor.png)](https://github.com/eldiscordia1/BlamHammer/blob/main/Screenshot%202026-10-24%20201107.png)

*The main BlamHammer interface, featuring multiple viewports, geometry editing tools, and the Halo shader browser.*

### In-Game Results

[![BlamHammer In-Game](screenshots/ingame.png)](https://github.com/eldiscordia1/BlamHammer/blob/main/Screenshot%202026-10-24%20201218.png)

*A custom Halo CE map created using BlamHammer and loaded in the game.*

## Features

### Geometry Editing
- Hammer-style brush creation and manipulation.
- Four synchronized viewports: 3D, Top, Front, and Side.
- Vertex, edge, and face editing.
- Grid snapping for precise geometry placement.
- Brush resizing and transformation.
- Undo and redo support.
- Geometry validation to prevent invalid operations.

### Subdivision Tool
- Subdivide geometry into editable sections.
- Create custom terrain, hills, slopes, and irregular surfaces.
- Manipulate subdivided vertices.
- Export subdivided geometry through the Halo CE JMS/BSP pipeline.

### Advanced Clipping Tool
Cut brushes using three selectable modes:

- **Keep Left** — Preserve the left portion.
- **Keep Right** — Preserve the right portion.
- **Keep Both** — Preserve both portions as separate brushes.

### Halo CE Integration
- Browse and apply real Halo CE shaders.
- Shader previews and material searching.
- Import existing BSP geometry for editing.
- Export custom geometry to JMS.
- Build BSPs using the official Halo CE tools.
- Compile scenarios and build playable `.map` files.
- Open scenarios directly in Sapien.
- Configure sky tags, scenario types, and project settings.
- Place basic scenario entities and player spawns.

### Project Management
- Native `.hceproject` format.
- Save and reopen editable projects.
- Configurable HCEEK installation paths.
- Project metadata and author information.
- Compiler output and error logging.

## Development Status

**BlamHammer! is currently in ALPHA.**

The editor is functional and has successfully been used to create, compile, and load custom maps in Halo: Combat Evolved.

Core features such as brush editing, clipping, subdivision, shader application, and geometry compilation are implemented.

However, the project is still under active development.

### Known Issues

BlamHammer! currently contains some minor bugs and limitations.

Most known issues are not significantly disruptive to normal map creation, although certain operations or complex geometry may still cause unexpected behavior.

Features may change, and stability improvements are ongoing.

**Alpha does not mean feature-complete or bug-free.**

## Source Code Availability

**BlamHammer! is currently CLOSED SOURCE.**

The source code is not publicly available at this stage.

The project may become open-source in the future, but no specific date or commitment has been established.

## Requirements

- Windows
- Halo: The Master Chief Collection
- Halo: Combat Evolved Editing Kit (HCEEK)
- A valid installation of the official Halo CE modding tools

## Future Plans

Potential improvements include:

- More advanced terrain editing.
- Improved BSP importing and editing.
- Expanded entity and scenery support.
- Better texture and UV manipulation.
- Additional Hammer-style editing tools.
- Performance improvements and bug fixes.

These are development goals and are not guaranteed features.

## Disclaimer

BlamHammer! is an unofficial community project.

It is not affiliated with, endorsed by, or sponsored by Microsoft, Xbox Game Studios, Halo Studios, Bungie, or Valve.

Halo and related trademarks belong to their respective owners.

Valve Hammer Editor and J.A.C.K. are referenced as inspirations for the interface and editing workflow.
