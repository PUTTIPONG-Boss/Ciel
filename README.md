# Ciel

A personal AI assistant that runs entirely on your own hardware. Ciel has a
defined character, speaks with a voice, and is reachable from any of your
devices over a private network.

Ciel is designed around a single always-on machine at home (an Apple Silicon
Mac with 16 GB of RAM is the reference target) serving a web app that you
install on your phone or laptop as a PWA.

```
phone / laptop ──(Tailscale, HTTPS)──► home server
                                        ├── Ciel   FastAPI app: web UI, WebSocket chat, persona, TTS
                                        └── Ollama local language model (qwen3:8b by default)
```

## Features

- **Local model.** Replies come from a model served by [Ollama](https://ollama.com).
  No conversation text leaves the machine for generation.
- **Configurable persona.** Name, personality, speech style, rules and example
  dialogue live in a single YAML file and reload without a restart.
- **Streaming speech.** Replies are split into sentences as they stream and
  synthesised one sentence at a time, so audio starts before the reply is
  finished. Emotion tags in the model output steer voice prosody and the
  on-screen visualiser.
- **Anime style mode.** Ciel always speaks Japanese and shows subtitles in the
  language you wrote in (Thai or English), each subtitle paired with its own
  spoken line.
- **Low latency on modest hardware.** The prompt is rendered so that every turn
  only appends to the previous one, keeping Ollama's prompt cache valid across
  the whole conversation. The model is pre-warmed at start-up and kept warm
  while idle. On an M1 Air the first spoken sentence typically arrives in
  about 3 seconds.
- **Installable web app.** Works as a PWA on iOS and Android, with optional
  password protection.
- **Self-updating server.** With auto-update enabled, the server pulls new
  commits from GitHub and restarts itself only when backend code changes.
- **Fine-tuning kit (experimental).** Tools for building a LoRA training set,
  training it with MLX and evaluating the result against the base model.

## Requirements

- Python 3.10 or newer
- [Ollama](https://ollama.com) with a chat model installed
- Internet access for speech synthesis (the default TTS backend is Edge TTS)
- [Tailscale](https://tailscale.com), for access from other devices (optional)

## Quick start

1. Install Ollama and pull a model:

   ```bash
   ollama pull qwen3:8b
   ```

2. Start Ciel.

   macOS / Linux:

   ```bash
   ./run.sh
   ```

   Windows:

   ```powershell
   .\run.ps1
   ```

   On first run the script creates a virtual environment, installs
   dependencies and copies `.env.example` to `.env`.

3. Open <http://localhost:47080>.

To try the interface without a model, set `CIEL_LLM=mock` in `.env`.

For a guided installation of a dedicated Mac server, see
[docs/SETUP_MAC.md](docs/SETUP_MAC.md).

### Choosing a model

| Machine | Suggested model |
|---|---|
| Apple Silicon, 16 GB | `qwen3:8b` |
| 32 GB or more | `qwen3:14b` or larger |

The prompt format is tuned for the Qwen3 family. For other models, set
`CIEL_RAW_PROMPT=false` to use Ollama's own chat template.

## Configuration

All settings are environment variables, read from `.env`. The most relevant
ones:

| Variable | Default | Description |
|---|---|---|
| `CIEL_LLM` | `ollama` | `ollama`, or `mock` for UI work without a model |
| `CIEL_MODEL` | `qwen3:8b` | Ollama model name |
| `CIEL_PERSONA` | `persona/ciel.yaml` | Persona file |
| `CIEL_TTS` | `edge` | `edge` or `off` |
| `CIEL_PORT` | `47080` | HTTP port |
| `CIEL_HOST` | `127.0.0.1` | Bind address. Use `0.0.0.0` to expose on the LAN |
| `CIEL_PASSWORD` | empty | Web UI password. Recommended for remote access |
| `CIEL_NUM_CTX` | `8192` | Model context window |
| `CIEL_MAX_HISTORY` | `20` | Messages kept before older turns are trimmed |
| `CIEL_AUTO_UPDATE` | `false` | Pull and apply updates from GitHub (server only) |
| `CIEL_TUNED` | `false` | Use the short prompt for a model fine-tuned with `training/` |

See [`.env.example`](.env.example) for the full list.

## Persona

The persona is defined in [`persona/ciel.yaml`](persona/ciel.yaml): identity,
personality, speech habits, rules, emotion tags, voice settings and example
conversations. Edits take effect when a new chat is started.

Example conversations have the strongest effect on how the model behaves,
especially with smaller models. When the output is not what you want, adding
an example of the desired reply is usually more effective than adding rules.

## Remote access

1. Install Tailscale on the server and on your devices, signed in to the same
   account.
2. On the server:

   ```bash
   tailscale serve --bg 47080
   ```

3. Open `https://<machine>.<tailnet>.ts.net` on your phone and add it to the
   home screen.

HTTPS is required for microphone access in browsers, which is why Tailscale's
HTTPS endpoint is used rather than the plain port.

For running a Mac as an always-on server (sleep settings, launchd service,
auto-update), see [docs/MAC_SERVER.md](docs/MAC_SERVER.md).

## Project structure

```
ciel/                 backend (FastAPI)
  main.py             HTTP API, WebSocket chat, warm-up and history management
  llm.py              Ollama client and prompt rendering
  persona.py          persona file to system prompt and messages
  speech.py           splits streamed text into speakable segments and subtitles
  tts.py              speech synthesis and emotion prosody
  voice_api.py        Voice Lab endpoints
  updater.py          GitHub auto-update
  auth.py             password and session cookie
  config.py           settings from the environment
persona/              persona definitions
web/                  web UI and PWA (chat, visualiser, Voice Lab)
scripts/              latency measurement, model comparison, Thai evaluation
training/             fine-tuning data, dataset builder and evaluation set
docs/                 setup guides and measurement reports
```

## Fine-tuning

`training/` contains multi-turn training dialogues, a dataset builder that
validates every reply against the same parser the app uses, and a held-out
evaluation set. Training runs on Apple Silicon with MLX; the result is
imported into Ollama and compared with the base model using
`scripts/eval_thai.py`. This is a work in progress and the fine-tuned model
is not yet used by default. See [training/README.md](training/README.md) and
[docs/MAC_TASK_FINETUNE.md](docs/MAC_TASK_FINETUNE.md).

## Versioning

The current version is in [`VERSION`](VERSION) and is shown in the web UI
together with the running commit. Changes are recorded in
[CHANGELOG.md](CHANGELOG.md).

## Roadmap

- [x] Chat with a configurable persona, streaming replies, PWA, password,
      auto-update
- [x] Sentence-level speech in Thai, Japanese and English with emotion tags,
      voice mode and Voice Lab
- [x] Latency work: prompt-cache-friendly rendering, warm-up and keep-warm
- [ ] Better Thai comprehension (LoRA fine-tuning, in progress)
- [ ] Persistent chat history and long-term memory
- [ ] Voice input (push-to-talk, then wake word)
- [ ] Offline speech synthesis with a dedicated voice
- [ ] Live2D avatar with lip sync
- [ ] Tools: calendar, files, web search, reminders
