# OpenChat

OpenChat is a lightweight desktop AI chat assistant for Linux and Windows. It uses Laguna through OpenRouter by default and can fall back to a local Ollama model when the cloud request fails.

## Features

- Clean desktop chat interface
- First-run OpenRouter API key setup
- API key stored locally, outside this repository
- OpenRouter model: `poolside/laguna-s-2.1:free`
- Local fallback through Ollama (default: `qwen2.5:1.5b`)
- Linux and Windows installers
- No Releases required

## Install

### Linux (Bash)

```bash
curl -fsSL https://raw.githubusercontent.com/openchat-oc/OpenChat/main/install | bash
```

### Windows (PowerShell)

```powershell
irm https://raw.githubusercontent.com/openchat-oc/OpenChat/main/install.ps1 | iex
```

The installer checks for Python and installs the Python dependencies for the application. On first launch, enter an OpenRouter API key from https://openrouter.ai/settings/keys.

## Local fallback

Install Ollama separately from https://ollama.com/ and pull a small model:

```bash
ollama pull qwen2.5:1.5b
```

OpenChat attempts the configured Ollama model if the OpenRouter request fails and Ollama is available.

## Privacy

The OpenRouter key is saved in the user's configuration directory, not in this repository. Do not share the key or commit it to source control.

## Development

```bash
python -m pip install -r requirements.txt
python -m app.main
``

## License

MIT