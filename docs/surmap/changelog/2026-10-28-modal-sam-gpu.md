# Modal GPU for the SAM 3.1 ONNX path

**Date:** 2026-10-28
**Feature:** Station SAM

The station can run SAM 3.1 on a Modal L4 from the PyTorch checkpoint
`facebook/sam3.1`. `ModalSamDetector` posts JPEG bytes and a text
prompt to `MODAL_SAM_URL` and reads boxes, polygons, scores, and GPU
seconds back. Select it with `--detector sam3-modal` or
`--sam3-device modal`. The local ONNX detector is unchanged.

The remote function is defined at module scope in
`surmap.survey.modal_sam_app`. Deploy with `modal deploy
src/surmap/survey/modal_sam_app.py` and stop it with `modal app stop
surmap-sam`. The idle scale-down is 60 seconds and at most one
container runs. The Hugging Face token is a Modal secret, not a file
in git. Muse Spark Open is a separate shared endpoint client,
`surmap.labelling.modal_muse`. Steps are in `docs/modal.md`.
