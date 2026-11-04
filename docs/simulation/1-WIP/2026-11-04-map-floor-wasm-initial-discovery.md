# Discovery: Bevy floor rendering

`examples/bevy-sitl-poc/src/world.rs build_world` spawns every element from the manifest; textures load through `textures.rs` (sRGB base colour, mip chains built on load). Ground today is a `box` element with a tiled PBR ground material. A dedicated floor plane (Rectangle mesh, one non-tiled texture, at ENU origin, slightly below box tops' base) avoids the materials system's world-size tiling. Bevy ENU: x east, y up, -z north.
