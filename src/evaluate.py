"""Run everything with one command:  python evaluate.py

1. Download LibriSpeech dev-clean and test-clean (once).
2. Enroll each speaker once, from 30 s of one chapter (one recording session).
3. Cut test speech from the speaker's OTHER chapters to 1, 2, 3 and 5 s and score it against
   every enrolled speaker: own speaker = owner trial, everyone else = stranger trial.
4. Set thresholds on dev-clean, measure errors on test-clean (40 different speakers).
5. Repeat with background noise and a phone-quality replay.
6. Write results.md, results.png and thresholds.json (used by demo.py).
"""
import json
import tarfile
import urllib.request
from pathlib import Path

import numpy as np
from scipy import signal

import check

DATA = Path("data/LibriSpeech")
LENGTHS = [1, 2, 3, 5]                         # seconds of speech in the check
ENROLL_SECONDS = 30
TESTS_PER_SPEAKER = 10
LIMITS = {"low-risk": 0.01, "private": 0.001}  # most strangers we accept letting in (FAR)
MAX_FRR = 0.05                                 # most owner attempts we accept shutting out
NOISE_SECONDS, NOISE_SNR_DB = 3, [20, 10, 5]
rng = np.random.default_rng(0)


def download(split):
    if not (DATA / split).exists():
        url = f"https://www.openslr.org/resources/12/{split}.tar.gz"
        print("downloading", url)
        archive, _ = urllib.request.urlretrieve(url)
        with tarfile.open(archive) as tar:
            tar.extractall(DATA.parent)


def build(split):
    """Each speaker's enrollment voiceprint, and test clips. No recording is in both."""
    enroll, tests = {}, []
    for spk_dir in sorted((DATA / split).iterdir()):
        chapters = sorted(spk_dir.iterdir())
        wav, rest = np.zeros(0, np.float32), []
        for f in sorted(chapters[0].glob("*.flac")):  # enrollment: the first chapter
            if len(wav) < ENROLL_SECONDS * check.SR:
                wav = np.concatenate([wav, check.load(f)])
            else:
                rest.append(f)
        enroll[spk_dir.name] = check.voiceprint(wav[: ENROLL_SECONDS * check.SR])

        # test: the other chapters (the same chapter only if the speaker has no other)
        files = [f for c in chapters[1:] for f in sorted(c.glob("*.flac"))] or rest
        rng.shuffle(files)
        n = 0
        for f in files:
            clip = check.load(f)
            if len(clip) >= max(LENGTHS) * check.SR:  # long enough for every length
                tests.append((spk_dir.name, clip[: max(LENGTHS) * check.SR]))
                n += 1
            if n == TESTS_PER_SPEAKER:
                break
    print(f"{split}: {len(enroll)} speakers, {len(tests)} test clips")
    return enroll, tests


def scores(enroll, tests, seconds, change=None):
    """Owner and stranger scores for test clips cut to `seconds` (optionally changed first)."""
    owner, stranger = [], []
    for spk, clip in tests:
        clip = clip[: seconds * check.SR]
        v = check.voiceprint(change(clip) if change else clip)
        for other, e in enroll.items():
            (owner if other == spk else stranger).append(check.score(v, e))
    return np.array(owner), np.array(stranger)


def add_noise(snr_db):
    def change(clip):
        noise = rng.standard_normal(len(clip)).astype(np.float32)
        return clip + noise * np.std(clip) / np.std(noise) / 10 ** (snr_db / 20)
    return change


def phone_replay(clip):
    """The owner's voice recorded from a phone call and played back: only 300-3400 Hz survive."""
    sos = signal.butter(4, [300, 3400], btype="bandpass", fs=check.SR, output="sos")
    return signal.sosfilt(sos, clip).astype(np.float32)


def pct(x, digits=2):
    return f"{100 * x:.{digits}f}%"


def main():
    for split in ("dev-clean", "test-clean"):
        download(split)
    dev, test = build("dev-clean"), build("test-clean")
    
    assert not set(dev[0]) & set(test[0]), "tuning and test speakers must be different people"

    dev_s = {s: scores(*dev, s) for s in LENGTHS}
    test_s = {s: scores(*test, s) for s in LENGTHS}
    thr = {s: {name: check.threshold_for_far(dev_s[s][1], far) for name, far in LIMITS.items()} for s in LENGTHS}
    n_own, n_str = len(test_s[LENGTHS[0]][0]), len(test_s[LENGTHS[0]][1])
    md = ["# Results", "", f"Thresholds set on dev-clean, errors measured on test-clean: "
          f"{n_own} owner trials, {n_str} stranger trials, 95% intervals in brackets.", ""]

    # 1. How much speech is needed
    md += ["## Speech length", "", "| Speech | Limit | Strangers let in (FAR) | Owner shut out (FRR) | Meets limits |",
           "|---|---|---|---|---|"]
    frr_curve, shortest = {name: [] for name in LIMITS}, {}
    for s in LENGTHS:
        own, strg = test_s[s]
        for name, far_limit in LIMITS.items():
            far, frr = check.error_rates(own, strg, thr[s][name])
            k_far, k_frr = round(far * n_str), round(frr * n_own)
            lo, hi = check.interval(k_far, n_str)
            flo, fhi = check.interval(k_frr, n_own)
            ok = far <= far_limit and frr <= MAX_FRR
            if ok and name not in shortest:
                shortest[name] = s
            frr_curve[name].append(frr)
            md.append(f"| {s} s | {name} | {pct(far, 3)} ({k_far}) [{pct(lo, 3)}–{pct(hi, 3)}] | "
                      f"{pct(frr)} ({k_frr}) [{pct(flo)}–{pct(fhi)}] | {'yes' if ok else 'no'} |")
    md += [""] + [f"**Shortest speech for {name}: {f'{shortest[name]} s' if name in shortest else 'none tested'}.**"
                  for name in LIMITS]

    # 2. Background noise (thresholds from quiet speech)
    md += ["", f"## Background noise ({NOISE_SECONDS} s, white noise)", "",
           "| SNR (Speech vs noise) | " + " | ".join(f"{n} FAR | {n} FRR" for n in LIMITS) + " |", "|---|" + "---|---|" * len(LIMITS)]
    rows = [("no noise", test_s[NOISE_SECONDS])] + [
        (f"{snr} dB", scores(*test, NOISE_SECONDS, add_noise(snr))) for snr in NOISE_SNR_DB]
    for label, (own, strg) in rows:
        cells = []
        for name in LIMITS:
            far, frr = check.error_rates(own, strg, thr[NOISE_SECONDS][name])
            cells += [pct(far, 3), pct(frr)]
        md.append(f"| {label} | " + " | ".join(cells) + " |")


    # 3. Replay: the owner's own voice, played back at phone quality, against the owner's enrollment
    replay, _ = scores(*test, NOISE_SECONDS, phone_replay)
    live = test_s[NOISE_SECONDS][0]
    md += ["", f"## Phone-quality replay of the owner ({NOISE_SECONDS} s)", "",
           f"Mean score: live owner {live.mean():.3f}, replayed owner {replay.mean():.3f}.", ""]
    md += [f"- Replay accepted at the {name} threshold: {pct(np.mean(replay >= thr[NOISE_SECONDS][name]), 1)}"
           for name in LIMITS]


    Path("results.md").write_text("\n".join(md) + "\n\n![FRR by speech length](results.png)\n", encoding="utf-8")
    Path("thresholds.json").write_text(json.dumps(thr, indent=2))
    plot(frr_curve)
    print("\n".join(md))


def plot(frr_curve):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 3.5))
    for (name, ys), color in zip(frr_curve.items(), ["#2a78d6", "#eb6834"]):
        ax.plot(LENGTHS, [100 * y for y in ys], "-o", color=color, linewidth=2,
                label=f"{name} (strangers ≤ {pct(LIMITS[name], 1)})")
    ax.axhline(100 * MAX_FRR, color="gray", linestyle="--", linewidth=1, label=f"owner limit {pct(MAX_FRR, 0)}")
    ax.set(xlabel="Seconds of speech", ylabel="Owner shut out (%)", xticks=LENGTHS,
           title="How often the owner is shut out (test-clean)")
    ax.legend(frameon=False)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig("results.png", dpi=150)


if __name__ == "__main__":
    main()
