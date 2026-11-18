"""Live meeting notetaker on AssemblyAI STT 3.7 Realtime.

Streams a 16-bit mono WAV at real-time pace (the way a meeting bot or
recorder would send audio), prints speaker-labeled turns as they finalize,
then sends the labeled transcript to LLM Gateway for meeting notes.
"""
import argparse
import os
import threading
import time
import wave
from pathlib import Path
from typing import List, Tuple

import requests
from dotenv import load_dotenv
from assemblyai.streaming.v3 import (
    BeginEvent,
    RealTimeError,
    RealTimeEvents,
    RealTimeParameters,
    RealTimeTranscriber,
    RealTimeTranscriberOptions,
    TerminationEvent,
    TurnEvent,
)

load_dotenv()
API_KEY = os.environ["ASSEMBLYAI_API_KEY"]

SPEECH_MODEL = "assemblyai-stt-3-7-realtime"
LLM_GATEWAY_URL = "https://llm-gateway.assemblyai.com/v1/chat/completions"
LLM_MODEL = "claude-sonnet-4-6"
CHUNK_MS = 50

turns: List[Tuple[str, str]] = []
done = threading.Event()


def on_begin(client: RealTimeTranscriber, event: BeginEvent):
    print(f"Session started: {event.id}\n")


def on_turn(client: RealTimeTranscriber, event: TurnEvent):
    # Partials stream in while someone talks; the final turn carries the label.
    if not event.end_of_turn or not event.transcript:
        return
    speaker = event.speaker_label or "PENDING"
    turns.append((speaker, event.transcript))
    print(f"[{speaker}] {event.transcript}")


def on_terminated(client: RealTimeTranscriber, event: TerminationEvent):
    print(f"\nSession ended: {event.audio_duration_seconds}s of audio processed")
    done.set()


def on_error(client: RealTimeTranscriber, error: RealTimeError):
    print(f"Error: {error}")
    done.set()


def stream_wav(client: RealTimeTranscriber, path: str) -> None:
    """Send the file in 50 ms chunks, paced like live audio."""
    with wave.open(path, "rb") as wf:
        frames_per_chunk = int(wf.getframerate() * CHUNK_MS / 1000)
        while True:
            chunk = wf.readframes(frames_per_chunk)
            if not chunk:
                break
            client.stream(chunk)
            time.sleep(CHUNK_MS / 1000)


def labeled_transcript() -> str:
    # Merge consecutive turns from the same speaker so the LLM sees clean blocks.
    lines: List[str] = []
    for speaker, text in turns:
        if lines and lines[-1].startswith(f"Speaker {speaker}:"):
            lines[-1] += " " + text
        else:
            lines.append(f"Speaker {speaker}: {text}")
    return "\n".join(lines)


def meeting_notes(transcript: str) -> str:
    prompt = (
        "You are a meeting notes assistant. From the speaker-labeled transcript "
        "below, write:\n1. A summary in 3-5 sentences\n2. Decisions made\n"
        "3. Action items with the owner's speaker label\n"
        "Ignore lines labeled PENDING when assigning owners.\n\n"
        f"Transcript:\n{transcript}"
    )
    response = requests.post(
        LLM_GATEWAY_URL,
        headers={"authorization": API_KEY},
        json={
            "model": LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1000,
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", help="16-bit mono PCM WAV file")
    parser.add_argument("--max-speakers", type=int, default=None,
                        help="Hard cap on speaker labels (1-10). Leave headroom.")
    parser.add_argument("--keyterms", nargs="*", default=[],
                        help="Names and terms to boost, e.g. --keyterms Priya Kubernetes")
    args = parser.parse_args()

    with wave.open(args.audio, "rb") as wf:
        if wf.getnchannels() != 1 or wf.getsampwidth() != 2:
            raise SystemExit("Use a 16-bit mono WAV (convert with ffmpeg -ac 1 -sample_fmt s16).")
        sample_rate = wf.getframerate()

    options = {}
    if args.max_speakers:
        options["max_speakers"] = args.max_speakers
    if args.keyterms:
        options["keyterms_prompt"] = args.keyterms

    params = RealTimeParameters(
        speech_model=SPEECH_MODEL,
        sample_rate=sample_rate,
        speaker_labels=True,
        **options,
    )

    client = RealTimeTranscriber(
        RealTimeTranscriberOptions(terminate_timeout=30.0),
        api_key=API_KEY,
    )
    client.on(RealTimeEvents.Begin, on_begin)
    client.on(RealTimeEvents.Turn, on_turn)
    client.on(RealTimeEvents.Termination, on_terminated)
    client.on(RealTimeEvents.Error, on_error)

    client.connect(params)
    try:
        stream_wav(client, args.audio)
    finally:
        # Terminate finalizes the open turn and closes the billed session.
        client.disconnect(terminate=True)

    transcript = labeled_transcript()
    out = Path("output")
    out.mkdir(exist_ok=True)
    (out / "transcript.txt").write_text(transcript + "\n")
    if not transcript:
        print("No speech transcribed.")
        return

    notes = meeting_notes(transcript)
    (out / "notes.md").write_text(notes + "\n")
    print("\n--- Meeting notes ---\n" + notes)


if __name__ == "__main__":
    main()
