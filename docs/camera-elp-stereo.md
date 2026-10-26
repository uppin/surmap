# Camera candidate: ELP dual-lens stereo USB module

Status: **candidate under evaluation — not yet committed.**
Recorded from the product listing supplied 2026-10-26, cross-checked
against reseller spec pages for the same module family.
Likely model: ELP-3DGS1200P01-H120 (the 120° variant; resellers list
HFOV 113–126° for this variant, so treat the exact FOV as unconfirmed).

Full architecture: [architecture.md](architecture.md).

## Claimed specifications

| Item | Listing claim | Note |
|---|---|---|
| Form | Dual-lens stereo module, 80 × 16.5 mm board, M12 lens mount | Small and light — good for a drone payload |
| Output | Single USB device, combined side-by-side stereo image | One UVC stream; software splits left/right halves |
| Interface | USB 2.0 (Type-C on module), UVC, plug-and-play | Works as a standard V4L2 device on Linux / CM5 |
| Sensor | OG02B10 CMOS, 1/2.9″ (from reseller specs, not the listing) | Confirm on the delivered unit |
| Shutter | Global shutter | Important: no rolling-shutter skew on a moving drone |
| Lenses | 120° HFOV, "no distortion", f/2.8 | "No distortion" is marketing — calibrate anyway (§ Risks) |
| Sync | Dual lenses hardware-synchronised | Must be verified, not assumed (§ Bench tests) |
| Audio | None relevant | MJPEG is the video format, despite the listing's wording |

## Resolution / frame-rate modes (MJPEG only)

Combined width is both eyes side by side, so per-eye width is half.

| Combined mode | Per eye | FPS | Intended use in SurMap |
|---|---|---|---|
| 3200×1200 | 1600×1200 | 60 | Mapping-quality keyframes only; too heavy to process every frame on the CM5 |
| 2560×720 | 1280×720 | 60 | Balanced survey mode — candidate default |
| 1600×600 | 800×600 | 120 | Fast motion / RTAB-Map tracking candidate |
| 1280×480 | 640×480 | 120 | Low-bandwidth fallback, detection + tracking only |
| 640×240 | 320×240 | 120 | Not useful for mapping; ignore |

Note the trade the listing hides: **120 fps exists only at low
resolution.** Full resolution runs at 60 fps.

## Why it fits

- Global shutter: RTAB-Map feature tracking and stereo matching on a
  vibrating, moving drone degrade badly with rolling shutter. This is
  the single strongest point in its favour.
- One USB cable, one UVC device, side-by-side frames: left/right
  pairing is inherent in each delivered frame — no two-device
  timestamp matching problem.
- UVC / V4L2 on Linux: no vendor driver needed on the CM5.
- High frame rate at reduced resolution suits visual odometry during
  fast passes; high resolution at 60 fps suits survey keyframes.
- M12 interchangeable lenses: the 120° lens can be swapped for a
  narrower one if the wide FOV hurts depth range too much.

## Risks and unknowns

1. **Baseline distance is not published anywhere in the listing or
   reseller specs found.** Baseline sets depth scale, minimum range,
   and usable depth range. It must be measured on the physical unit
   and confirmed by calibration before any depth numbers are trusted.
   An 80 mm-wide board implies a short baseline, which implies depth
   accuracy falls off quickly with distance — acceptable for near-field
   survey, limiting for high-altitude mapping.
2. **USB 2.0 + MJPEG only.** Consequences: compression artefacts in
   exactly the textured areas stereo matching relies on; MJPEG decode
   cost on the CM5 for every frame, competing with RTAB-Map and the
   Coral pipeline; total bandwidth caps usable mode combinations.
   There is no uncompressed mode at useful resolutions.
3. **"Synchronised" is a claim, not a measurement.** If the two sensors
   are not truly exposure-synchronised, stereo and RTAB-Map results on
   a moving drone will show it. Bench-verify (§ below).
4. **"No distortion" 120° lenses still distort.** A 120° HFOV lens
   stretches pixels at the edges, which lowers effective depth
   precision there and shrinks the genuinely overlapping field of view.
   Calibrate with a fisheye-aware model and expect to crop edges.
5. **Exposure/gain control is unspecified.** Stereo matching wants both
   eyes locked to the same exposure and gain. Whether UVC controls on
   this module can lock both (or only a shared value) is unknown until
   tested. Independent auto-exposure per eye would be a real problem.
6. **No hardware timestamps, no external trigger, no IMU.** Frame time
   is host arrival time (USB + MJPEG decode jitter included). RTAB-Map
   runs visual-only unless a separate IMU is added and time-synced.
7. **CM5 sustained load is unproven.** 3200×1200@60 MJPEG decode plus
   RTAB-Map plus Coral preprocessing on a CM5 may throttle thermally
   on a drone with limited airflow. Sustained — not burst — rates count.

## Candidate operating points (to benchmark, not decided)

- **Survey default:** 2560×720 @ 60 fps combined (1280×720 per eye).
  Process keyframes for depth/SAM; run detection/tracking on a
  downscaled left channel.
- **Fast / low-altitude passes:** 1600×600 @ 120 fps (800×600 per eye)
  for RTAB-Map robustness; depth from selected keyframes only.
- **Quality keyframes:** occasional 3200×1200 frames for the sharpest
  point clouds, if mode switching proves fast enough not to drop the
  tracking stream. Otherwise fix one mode per flight.

Mode choice is a bench result, not a listing decision.

## Bench tests required before committing

1. Enumerate actual V4L2 formats/fps on the CM5 (`v4l2-ctl --list-formats-ext`)
   and confirm the table above; record any YUYV modes the listing omits.
2. Sustained capture for 10 min per candidate mode on the CM5:
   delivered fps, dropped frames, CPU, temperature, throttling flags —
   with RTAB-Map and Coral detection running concurrently.
3. Left/right sync test: flashing LED / fast moving edge; confirm both
   halves show the same instant.
4. Measure the lens baseline physically; run stereo calibration
   (fisheye model); report reprojection error and rectified epipolar
   alignment.
5. Depth accuracy check against tape-measured targets at roughly
   1 / 3 / 5 / 10 / 20 m; state the distance where error becomes
   unacceptable for survey use. This sets the survey altitude envelope.
6. Exposure test: verify exposure and gain can be locked and matched
   across both eyes via UVC controls; check behaviour in changing light.
7. Vibration test on a representative mount: image blur and RTAB-Map
   tracking survival under drone-like vibration.

**Commit rule:** this camera becomes the project camera only if tests
2–6 pass at the survey operating point. If depth range (test 5) fails,
the fallback is a narrower-lens variant of the same module or a
different rig — not more software.

## Sources

- Product listing text supplied by the project owner (Amazon-style
  listing, ELP store, 2026-10-26).
- [ELP reseller specification page for this module](https://www.hdusbcameras.com/elp-synchronous-3d-stereo-vr-usb-camera.html)
  (sensor OG02B10, mode table, model variants).
