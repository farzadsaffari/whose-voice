"""Try the check on your own voice. Record with any app, any sample rate.

    python src/demo.py enroll.wav live.wav replayed.wav [clone.wav ...]

enroll.wav: about 30 s of you speaking. Each other file is one attempt; its first 3 s of
speech are checked with the thresholds from evaluate.py saved.
"""
import json
import sys

import numpy as np

import agent
import check

SECONDS = "3"


def speech_only(wav):
    """Drop silence at the start and end."""
    loud = np.flatnonzero(np.abs(wav) > 0.02 * np.abs(wav).max())
    return wav[loud[0]: loud[-1] + 1]


def main(enroll_file, *attempts):
    thr = json.load(open("thresholds.json"))[SECONDS]
    owner = check.voiceprint(speech_only(check.load(enroll_file))[: 30 * check.SR])
    for f in attempts:
        clip = speech_only(check.load(f))[: int(SECONDS) * check.SR]
        s = check.score(check.voiceprint(clip), owner)
        voice = "private" if s >= thr["private"] else "low-risk" if s >= thr["low-risk"] else "unsure"
        print(f"{f}: score {s:.3f}, voice passes: {voice}")
        print(f"   read_messages -> {agent.next_step('read_messages', voice)}")
        print(f"   pay           -> {agent.next_step('pay', voice)}")


if __name__ == "__main__":
    main(*sys.argv[1:])
