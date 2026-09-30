"""Fetch pinned English data for the Tesseract engine bundled with PyMuPDF."""
import hashlib
from pathlib import Path
from urllib.request import urlopen

URL = 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/eng.traineddata'
SHA256 = '7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2'


def main():
    target = Path(__file__).resolve().parent / 'cache' / 'tessdata' / 'eng.traineddata'
    data = target.read_bytes() if target.exists() else urlopen(URL, timeout=60).read()
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError('OCR language data checksum mismatch')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    print('Verified English OCR data:', target)


if __name__ == '__main__':
    main()
