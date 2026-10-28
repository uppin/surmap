# Modal GPU for the SAM 3.1 ONNX path

**Date:** 2026-10-28
**Feature:** Station SAM

The station can run the exported SAM 3.1 ONNX model on a Modal GPU.
`ModalSamSession` posts the image tensor to `MODAL_SAM_URL`.
`Sam3Detector` turns the returned masks into the same polygons as the
local CPU and CUDA session. Select it with `--detector sam3-modal` or
`--sam3-device modal`.

The remote app is `surmap-sam`. Deploy with `modal deploy
src/surmap/survey/modal_sam_app.py` and stop it with `modal app stop
surmap-sam`. The default GPU is a T4, the idle scale-down is 60
seconds, and at most one container runs. Nothing is kept warm. The
checkpoint stays on a Modal Volume. CI does not install Modal. Spend
for workspace `ginas-bb` is the Usage page at
https://modal.com/settings/usage. Commands are in `HACKATHON.md` and
the `surmap.survey.modal_sam` module docstring.
