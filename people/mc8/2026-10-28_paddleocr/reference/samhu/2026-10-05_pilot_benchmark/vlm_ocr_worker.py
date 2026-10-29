"""Local image-only text recognition worker; no labels or prior predictions read.

Runs in the existing MinerU environment. PP-OCRv6 detects boxes only;
MinerU2.5-Pro recognizes every crop. The recognizer from Paddle is never loaded.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model-config', required=True)
    args = ap.parse_args()
    import numpy as np
    import torch
    from PIL import Image
    from mineru.model.utils.tools.infer.predict_det import TextDetector
    from mineru.model.utils.tools.infer.pytorchocr_utility import init_args
    from mineru.utils.ocr_utils import sorted_boxes, get_rotate_crop_image_for_text_rec
    from mineru_vl_utils.mlx_compat import load_mlx_model
    from mineru_vl_utils.vlm_client.mlx_client import MlxVlmClient
    from mineru_vl_utils.mineru_client import MinerUSamplingParams

    config = json.loads(Path(args.model_config).read_text())['models-dir']
    det_path = Path(config['pipeline']) / 'models/OCR/paddleocr_torch/ch_PP-OCRv6_small_det_infer.safetensors'
    torch.set_num_threads(4)
    det_args = init_args().parse_args([])
    det_args.device = 'cpu'
    det_args.det_model_path = str(det_path)
    detector = TextDetector(det_args)
    model, processor = load_mlx_model(config['vlm'])
    client = MlxVlmClient(model, processor, use_tqdm=False,
                         sampling_params=MinerUSamplingParams(max_new_tokens=512,
                                                             presence_penalty=1.0, frequency_penalty=0.05))
    info = dict(model='opendatalab/MinerU2.5-Pro-2605-1.2B', model_snapshot=Path(config['vlm']).name,
                detector=det_path.name, detector_sha256=hashlib.sha256(det_path.read_bytes()).hexdigest(),
                detector_limit_side_len=det_args.det_limit_side_len,
                versions={k: importlib.metadata.version(k) for k in ('mineru','mineru-vl-utils','mlx','mlx-vlm','torch')},
                prompt='\nText Recognition:', max_new_tokens=512, temperature=0.0, top_p=0.01, top_k=1,
                presence_penalty=1.0, frequency_penalty=0.05)
    print('READY ' + json.dumps(info), flush=True)
    for line in sys.stdin:
        request = json.loads(line)
        started = time.perf_counter()
        try:
            image = Image.open(request['image']).convert('RGB')
            bgr = np.asarray(image)[:, :, ::-1].copy()
            boxes, detection_seconds = detector(bgr)
            boxes = sorted_boxes(boxes) if boxes is not None else []
            predictions = []
            for box in boxes:
                crop = get_rotate_crop_image_for_text_rec(bgr, box.copy())
                crop_image = Image.fromarray(crop[:, :, ::-1])
                text = client.predict(crop_image, prompt='\nText Recognition:')
                predictions.append(dict(box=box.tolist(), text=text, confidence=None))
            result = dict(status='success', image_sha256=hashlib.sha256(Path(request['image']).read_bytes()).hexdigest(),
                          image_size=list(image.size), predictions=predictions, detection_seconds=detection_seconds,
                          elapsed_seconds=time.perf_counter()-started)
        except Exception as exc:
            result = dict(status='failed', error=repr(exc))
        Path(request['output']).write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
        print('DONE ' + request['output'], flush=True)


if __name__ == '__main__':
    main()
