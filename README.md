# Car Repair Diagnostic Speechbot — TTS & PreResponse Modules

Group coursework for F20CA Conversational Agents & Spoken Language — Heriot-Watt University.
8-person team. **My contribution: the TTS module (`modules/TTS/`) and PreResponse system (`modules/preResponse/`).**

A spoken-dialogue bot that guides users through car repair diagnostic questions via a structured conversational pipeline: VAD → ASR → LLM → TTS.

---

## My Modules

### TTS (`modules/TTS/tts.py`)

Supports three cloud TTS providers with streaming PCM output:

| Provider | Method |
|---|---|
| Edge TTS | `edge_tts` subprocess with ffmpeg PCM conversion |
| Microsoft Azure | REST API with streaming chunked PCM |
| Google Cloud | `google-cloud-texttospeech` streaming |

All three providers use the same interface — a `text_queue` for input and a `chunk_queue` for streamed PCM output — with cancellation support via a threading event flag.

### TTS Latency Benchmark (`modules/TTS/tts_latency_test.py`)

Ran a 100-iteration benchmark across all three providers, recording avg, median, min, and max latency to inform final model selection for the team.

### PreResponse (`modules/preResponse/preResponse.py`)

Manages a library of pre-recorded short responses (hello, acknowledgements, goodbye) to play instantly while the LLM generates a full response — reducing perceived latency.

- Pre-generates WAV files via TTS on first run and caches them
- Randomises acknowledgement responses ("Got it.", "Understood.", etc.) to avoid robotic repetition
- Loads audio into memory as chunked PCM for zero-latency playback

---

## Structure

```
car-repair-speechbot/
├── modules/
│   ├── TTS/
│   │   ├── tts.py                  Main TTS module (Edge, Microsoft, Google)
│   └── preResponse/
│       └── preResponse.py          Pre-recorded response cache and playback
├── requirements.txt
└── README.md
```

---

## Setup

```bash
pip install requests edge-tts google-cloud-texttospeech google-auth
```

Edge TTS also requires `ffmpeg` installed on your system.

For Google Cloud TTS, set up a service account and export:
```bash
export GOOGLE_APPLICATION_CREDENTIALS="path/to/your/key.json"
```

---

## Notes

The full pipeline (VAD, ASR, LLM) was implemented by other team members and is not included here. This repo contains only the modules I personally built and am able to share.
