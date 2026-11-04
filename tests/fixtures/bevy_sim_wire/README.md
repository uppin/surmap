# Bevy simulation wire goldens

`hello.bin` (the camera profile `assets/cameras/elp-stereo-pinhole.camera.json` plus one
ground-truth car) and `pair.bin` are the browser → bridge messages the Bevy PoC
(`examples/bevy-sitl-poc/src/wire.rs`) must produce byte for byte and
`surmap.simulation.bevy_wire` must decode. Layout: `u32` little-endian header
length, compact JSON header, then (pair only) left and right grey8 payloads of
`width * height` bytes each. `pair.bin` is a 4×2 frame: left bytes 0..7, right
bytes 8..15. Change both sides together.

`pair-drone.bin` is `pair.bin` from a fleet page: the same frame and payloads, its header
ending `"drone_id":"nest-sw-d1"` (the drone whose eyes rendered it). A pair without a drone id
omits the key, so `pair.bin` stays the single-drone message; the bridge routes it to the
`default` drone.
