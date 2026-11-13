"""The voice check: voiceprints, scores, thresholds and error rates."""
import numpy as np
from scipy import signal, stats

SR = 16000  # LibriSpeech and the model both use 16 kHz audio
_model = None


def load(path):
    """Read an audio file as mono 16 kHz."""
    import soundfile as sf

    wav, sr = sf.read(str(path), dtype="float32")

    
    if wav.ndim > 1:  # stereo -> mono
        wav = wav.mean(axis=1)
    if sr != SR:      # e.g. a 48 kHz phone recording
        wav = signal.resample_poly(wav, SR, sr).astype(np.float32)
    return wav


def voiceprint(wav):
    """192-number voiceprint from the pretrained ECAPA-TDNN (SpeechBrain, trained on VoxCeleb)."""
    global _model
    import torch
    from speechbrain.inference.speaker import EncoderClassifier
    from speechbrain.utils.fetching import LocalStrategy

    if _model is None:  # load the model once
        _model = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir="pretrained_models/spkrec-ecapa-voxceleb",
            local_strategy=LocalStrategy.COPY,  # copy files instead of symlinks, so it works on Windows too
        )
    x = torch.from_numpy(np.ascontiguousarray(wav, dtype=np.float32)).unsqueeze(0)
    with torch.no_grad():
        v = _model.encode_batch(x).squeeze().numpy()
    return v / np.linalg.norm(v)  # unit length, so a dot product is the cosine


def score(a, b):
    """Cosine similarity of two voiceprints: close to 1 means the same voice."""
    return float(a @ b)


def threshold_for_far(stranger_scores, far):
    """Lowest threshold that lets in at most a share `far` of strangers."""
    s = np.sort(stranger_scores)[::-1]  # highest first
    allowed = int(far * len(s))         # how many strangers may pass
    return float(s[allowed]) + 1e-9     # just above the first one that must not pass



def error_rates(owner_scores, stranger_scores, threshold):
    """FAR = share of strangers let in. FRR = share of owner attempts shut out."""
    far = float(np.mean(np.asarray(stranger_scores) >= threshold))
    frr = float(np.mean(np.asarray(owner_scores) < threshold))
    return far, frr


def interval(errors, trials, confidence=0.95):
    """Exact binomial interval (Clopper-Pearson). Assumes independent trials: see README."""
    a = (1 - confidence) / 2
    lo = stats.beta.ppf(a, errors, trials - errors + 1) if errors > 0 else 0.0
    hi = stats.beta.ppf(1 - a, errors + 1, trials - errors) if errors < trials else 1.0
    return float(lo), float(hi)

