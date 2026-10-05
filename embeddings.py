"""Local multilingual E5 ONNX embeddings. Never uploads query or memory text."""
import hashlib
import json
from pathlib import Path
import urllib.request
import os

REPOSITORY = 'Xenova/multilingual-e5-small'
REVISION = '761b726dd34fb83930e26aab4e9ac3899aa1fa78'
FILES = ('tokenizer.json', 'config.json', 'onnx/model_quantized.onnx')


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def download(directory):
    """Explicit public model download; pinned revision, verified LFS model hash."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    request = f'https://huggingface.co/api/models/{REPOSITORY}/revision/{REVISION}?blobs=true'
    with urllib.request.urlopen(request, timeout=60) as response:
        info = json.load(response)
    assert info['sha'] == REVISION
    siblings = {e['rfilename']: e for e in info['siblings']}
    hashes = {}
    for name in FILES:
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        expected = siblings[name].get('lfs', {}).get('sha256')
        if path.exists() and expected and digest(path) == expected:
            hashes[name] = expected
            continue
        temp = path.with_suffix(path.suffix + '.part')
        try:
            url = f'https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/{name}'
            with urllib.request.urlopen(url, timeout=60) as response, temp.open('wb') as out:
                while True:
                    block = response.read(1024 * 1024)
                    if not block: break
                    out.write(block)
            hashes[name] = digest(temp)
            if expected and hashes[name] != expected:
                raise ValueError('Model download failed SHA-256 verification')
            os.replace(temp, path)
        finally:
            if temp.exists(): temp.unlink()
    manifest = dict(repository=REPOSITORY, revision=REVISION, sha256=hashes,
                    encoding='e5-query-passage-mean-pool-l2-overflow-v1')
    (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


class LocalE5:
    def __init__(self, directory, threads=4):
        try:
            import numpy as np
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except ImportError as exc:
            raise ValueError('Install requirements-vector.txt to use semantic search') from exc
        self.np = np
        directory = Path(directory)
        manifest = json.loads((directory / 'manifest.json').read_text())
        if manifest['repository'] != REPOSITORY or manifest['revision'] != REVISION:
            raise ValueError('Unsupported E5 model manifest')
        for name in FILES:
            if digest(directory / name) != manifest['sha256'][name]:
                raise ValueError('Model files changed; download and verify again')
        self.fingerprint = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
        self.tokenizer = Tokenizer.from_file(str(directory / 'tokenizer.json'))
        self.tokenizer.enable_truncation(max_length=512, stride=64)
        config = json.loads((directory / 'config.json').read_text())
        self.pad_id = config.get('pad_token_id', 1)
        self.tokenizer.no_padding()
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(directory / 'onnx/model_quantized.onnx'),
                                            sess_options=options, providers=['CPUExecutionProvider'])
        self.inputs = {x.name for x in self.session.get_inputs()}
        self.dimension = 384

    def encode(self, texts, query=False):
        np = self.np
        if not texts: return np.empty((0, self.dimension), dtype=np.float32)
        prefix = 'query: ' if query else 'passage: '
        originals = self.tokenizer.encode_batch([prefix + text for text in texts])
        windows, owners = [], []
        for owner, encoding in enumerate(originals):
            for window in [encoding] + list(encoding.overflowing):
                windows.append(window); owners.append(owner)
        order = sorted(range(len(windows)), key=lambda i: len(windows[i].ids))
        windows = [windows[i] for i in order]
        owners = [owners[i] for i in order]
        output = np.zeros((len(texts), self.dimension), dtype=np.float32)
        counts = np.zeros(len(texts), dtype=np.float32)
        for start in range(0, len(windows), 8):
            batch = windows[start:start + 8]
            length = max(len(x.ids) for x in batch)
            ids = np.full((len(batch), length), self.pad_id, dtype=np.int64)
            masks = np.zeros_like(ids)
            for row, enc in enumerate(batch):
                ids[row, :len(enc.ids)] = enc.ids
                masks[row, :len(enc.attention_mask)] = enc.attention_mask
            feed = dict(input_ids=ids, attention_mask=masks)
            if 'token_type_ids' in self.inputs: feed['token_type_ids'] = np.zeros_like(ids)
            hidden = self.session.run(None, {k:v for k,v in feed.items() if k in self.inputs})[0]
            vectors = (hidden * masks[..., None]).sum(axis=1) / np.maximum(masks.sum(axis=1)[:, None], 1)
            vectors = vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
            for row, vector in enumerate(vectors):
                owner = owners[start + row]
                output[owner] += vector; counts[owner] += 1
        output /= counts[:, None]
        output /= np.maximum(np.linalg.norm(output, axis=1, keepdims=True), 1e-12)
        return output
