# Station responses and verification indicate GPU vs CPU execution

Every `SamFrameDetections` now carries `provider` and `device`
(e.g. `SAM 3.1 (PyTorch)` / `cuda:0`), populated by the station
server from the detector; the SAM detectors expose the device they
run on. The new `scripts/verify_station.py` feeds the demo stream
to a station server and checks health, the analysis stream, and
the accelerator, printing `DEVICE station: GPU (…)` or `CPU (…)`
and the analysis rate; `--expect-device gpu|cpu` fails the run
when the station answered on the other kind of hardware, so a
silent CPU fallback cannot pass as a GPU deployment.

Verification: gates green (ruff, format, mypy strict, pytest).
Live against the station at 10.88.77.10 (NVIDIA GPU, SAM 3.1
PyTorch): `DEVICE station: GPU (provider=SAM 3.1 (PyTorch),
device=cuda:0)`, ~3.9 fps at the time; a CPU-only local server
reports the CPU indicator in the replay test.
