# vendor/mobile_sam

Vendored copy of [MobileSAM](https://github.com/ChaoningZhang/MobileSAM)
(Apache-2.0), trimmed to the inference path this tool uses.

## Why it is vendored

`pip install git+https://github.com/ChaoningZhang/MobileSAM.git` kept failing on
user machines — it needs git, network access to GitHub, and it pulls `timm`,
whose install failed independently. The result was the tool silently falling
back to "AI unavailable" even though `mobile_sam.pt` was sitting right there in
the repo. Shipping the source removes every one of those failure modes: the only
runtime requirements are `torch`, `numpy` and `cv2`, which are core deps already.

`app.py` puts this directory on `sys.path` before importing, so the vendored
copy wins over anything pip may have installed.

## Changes from upstream

1. **`modeling/tiny_vit_sam.py`** — upstream imports `DropPath`, `to_2tuple`,
   `trunc_normal_` from `timm.models.layers` and `register_model` from
   `timm.models.registry`. Those four symbols are reimplemented at the top of
   the file (`trunc_normal_` delegates to `torch.nn.init`, `register_model`
   becomes a no-op decorator since only the unused model-zoo helper calls it).
   `timm` is no longer a dependency.

2. **Removed, unused by the `SamPredictor` path:**
   - `automatic_mask_generator.py`
   - `utils/amg.py`
   - `utils/onnx.py`

   These were also the only things importing `pycocotools`.

3. **`__init__.py`** — no longer re-exports `SamAutomaticMaskGenerator`.

Nothing else was touched. Model weights are unchanged, so checkpoints load
exactly as upstream: verified at 10,130,092 parameters with a real
`predict()` call producing a mask.

## Updating

Re-copy the upstream package, re-apply the three changes above, then confirm
with a no-`timm` import test before committing.
