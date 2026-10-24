# BlamHammer!

**A Hammer-inspired 3D level editor for Halo: Combat Evolved (MCC).**

![Status](https://img.shields.io/badge/Status-Alpha-orange)
![Platform](https://img.shields.io/badge/Platform-Windows-blue)
![Source](https://img.shields.io/badge/Source-Open%20Source-brightgreen)
![AI](https://img.shields.io/badge/Developed%20with-GPT--6%20Astra-purple)

## About

**BlamHammer! (BHammer)** is an open-source 3D level editor inspired by Valve's Hammer Editor and J.A.C.K., designed for **Halo: Combat Evolved in The Master Chief Collection**.

Developed with **GPT-6 Astra by OpenAI**, BlamHammer aims to simplify Halo CE level creation through an intuitive brush-based workflow, reducing the need for external modeling software like Blender.

The editor integrates with the official Halo CE Editing Kit (HCEEK), supporting geometry creation, shader application, JMS export, BSP compilation, and scenario editing workflows.

## Screenshots

### Editor Interface

![BlamHammer Editor](Screenshot%202026-10-24%20201107.png)

*BlamHammer's editor interface, featuring multiple viewports and geometry editing tools.*

### In-Game — Halo CE Tag Test

![BlamHammer In-Game](Screenshot%202026-10-24%20201218.png)

*A custom map created with BlamHammer, compiled and loaded in Halo CE Tag Test.*

## Features

### Geometry Editing

- Hammer-style brush creation and editing.
- Four viewports: 3D, Top, Front, and Side.
- Vertex, edge, and face manipulation.
- Grid snapping.
- Brush resizing and transformations.
- Undo and redo.
- Automatic geometry validation.

### Subdivision Tool

- Subdivide surfaces into editable grids.
- Create custom terrain, hills, slopes, and irregular geometry.
- Edit individual vertices.
- Export subdivided geometry to Halo CE.

### Clipping Tool

Three selectable clipping modes:

- **Keep Left** — Keep the left portion.
- **Keep Right** — Keep the right portion.
- **Keep Both** — Preserve both parts as separate brushes.

### Halo CE Integration

- Browse and apply original Halo CE shaders.
- Texture previews and material searching.
- **Import existing BSP geometry.**
- Export geometry to JMS.
- Compile BSPs and scenarios.
- Build playable `.map` files.
- Open scenarios in Sapien.
- Configure sky tags and scenario types.
- Basic entity and spawn placement.
- Compiler logs and error reporting.

### Project Management

- Native `.hceproject` project format.
- Save and load editable projects.
- Configurable HCEEK paths.
- Project metadata and author information.

## Development Status

**BlamHammer! is currently in ALPHA.**

The editor is functional and has successfully created, compiled, and loaded custom levels in Halo CE.

Although some minor bugs and limitations remain, most do not significantly affect normal map creation.

More complex operations may still produce unexpected results.

The project is actively evolving, and some features may change in future versions.

## Open Source

**BlamHammer! is an open-source project.**

Its source code is publicly available for developers and Halo modders to inspect, study, and contribute to.

The project was developed with the assistance of **OpenAI's GPT-6 Astra**, which helped implement the editor, geometry tools, Halo CE integration, and compilation workflows.

Contributions, bug reports, and suggestions are welcome.

See the repository's LICENSE file for the applicable terms.

## Requirements

- Windows
- Halo: The Master Chief Collection
- Halo: Combat Evolved Editing Kit (HCEEK)
- Official Halo CE modding tools

## Future Plans

- More advanced terrain editing.
- Improved BSP importing.
- Expanded entity support.
- Better UV and material editing.
- Performance optimizations.
- Bug fixes and stability improvements.

## Credits

**Project:** BlamHammer! (BHammer)

**Development:** Created with GPT-6 Astra by OpenAI.

**Inspired by:** Valve Hammer Editor and J.A.C.K.

**Game integration:** Halo: Combat Evolved Editing Kit (HCEEK).

## Disclaimer

BlamHammer! is an unofficial community project and is not affiliated with Microsoft, Halo Studios, Bungie, Valve, or OpenAI.

Halo and related trademarks belong to their respective owners.

