# AI notetaker on AssemblyAI STT 3.7 Realtime

Companion code for the AssemblyAI blog post "Best speech-to-text API for AI notetakers".

It streams meeting audio to **AssemblyAI STT 3.7 Realtime** (`assemblyai-stt-3-7-realtime`, the streaming model built for notetakers and ambient transcription), prints speaker-labeled turns as they finalize, and then sends the labeled transcript to **LLM Gateway** for a summary, decisions and action items.

## What it shows

- `speaker_labels=True` on the streaming WebSocket. Each final turn carries a `speaker_label` (`A`, `B`, ...). Turns under about one second of audio come back as `PENDING`.
- Optional `max_speakers` (a hard cap, 1-10) and `keyterms_prompt` for attendee names and jargon.
- `disconnect(terminate=True)` so the last turn finalizes and the billed session closes. Streaming is billed on session duration.
- One LLM Gateway call over the finished transcript.

## Setup

Python 3.9+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then add your API key
```

## Run

The script takes a 16-bit mono WAV and streams it at real-time pace, the way a meeting bot or recorder would send audio.

```bash
# Convert any recording first if needed:
ffmpeg -i meeting.m4a -ac 1 -ar 16000 -sample_fmt s16 meeting.wav

python notetaker.py meeting.wav --max-speakers 4 --keyterms "Priya Raman" Kubernetes
```

Output:

- live `[A] ...` / `[B] ...` lines in the terminal
- `output/transcript.txt`, the merged speaker-labeled transcript
- `output/notes.md`, the LLM Gateway meeting notes

## Notes

- Requires `assemblyai==1.10.1` or later. Earlier SDK versions don't list the STT 3.7 model IDs.
- STT 3.7 Realtime is $0.30/hr of session time. See https://www.assemblyai.com/pricing.
- For a live microphone or a meeting-bot feed, replace `stream_wav()` with your audio source and keep sending 16-bit PCM chunks of about 50 ms.
- Voice agents should use `assemblyai-stt-3-7-realtime-agent` instead.

Docs: [Streaming diarization](https://www.assemblyai.com/docs/streaming/label-speakers-and-separate-channels) · [Meeting notetaker best practices](https://www.assemblyai.com/docs/meeting-notetaker-best-practices) · [LLM Gateway](https://www.assemblyai.com/docs/llm-gateway/quickstart)
