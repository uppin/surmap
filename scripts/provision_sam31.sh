#!/usr/bin/env bash
# Provision the PyTorch SAM 3.1 stack into the station venv.
#
# Run by scripts/deploy-station.sh on the station (as the pre-restart
# hook) when the station is deployed with --detector sam31-torch:
# torch + Meta's sam3 package are an optional install, deliberately
# not project dependencies (see surmap.survey.sam3_torch). Fails the
# deploy when the GPU stack does not come up.
set -eu

cd "$(dirname "$0")/.."
.venv/bin/python -m pip install -q \
    torch torchvision "setuptools<81" \
    einops ftfy iopath psutil pycocotools regex safetensors huggingface-hub \
    "git+https://github.com/facebookresearch/sam3.git"
.venv/bin/python -c \
    "import torch, sam3; assert torch.cuda.is_available(), 'torch sees no CUDA device'"
echo "SAM 3.1 torch stack provisioned (CUDA available)"
