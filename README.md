# SwadesAI — Voice Agent Hackathon

Conversational voice agent for **Swades Health** with **appointment booking**, **live monitoring**, **watcher takeover**, and **warm transfer** to a human via Twilio SIP.

Built with **Python (LiveKit Agents)**, **Next.js**, **Groq**, **Deepgram / Sarvam AI**, and **LiveKit Cloud**.

📖 **Full documentation:** [docs/PROJECT.md](docs/PROJECT.md)

## Architecture

```
Caller (phone or browser) → LiveKit Room ← Python Agent A (STT → LLM → TTS)
                                    ↑
                         Next.js Monitor (transcript, state, takeover)
                                    ↓
                    Warm Transfer → Supervisor phone (Twilio SIP outbound)
```

## Quick start

### 1. Environment

```bash
cp .env.example .env
cp frontend/.env.local.example frontend/.env.local
```

Fill in both files. See [docs/PROJECT.md#environment-configuration](docs/PROJECT.md#environment-configuration) for the full variable list.

### 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python agent.py dev
```

Console test (no LiveKit room): `python agent.py console`

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) — `/call`, `/monitor`, `/appointments`.

## Features at a glance

| Feature | Route / entry |
|---------|----------------|
| Web call with Agent A | `/call` |
| Live monitor + takeover | `/monitor` |
| Appointment list | `/appointments` |
| Warm transfer to supervisor | Ask for a human during a call |
| Post-call summary | Monitor UI after hangup |

## Project structure

```
backend/
  agent.py           # Voice agent + tools + warm transfer
  monitor.py         # Live events + booking fallbacks
  booking.py         # SQLite appointments
  intake_tracker.py  # Spoken-field parsing
  speech_filters.py  # Strip leaked tool JSON
  voice_config.py    # Language + STT/TTS
  summary.py         # Post-call + transfer briefs
frontend/
  src/app/call/      # Start web call
  src/app/monitor/   # Watcher dashboard
  src/app/appointments/
  src/components/    # VoiceRoom, MonitorPanels
```

## SIP / Twilio (phone + warm transfer)

1. Inbound SIP trunk + dispatch rule → agent `swades-agent`
2. Outbound SIP trunk for warm transfer
3. Twilio trial: verify supervisor number in Verified Caller IDs

Details: [docs/PROJECT.md#sip--twilio-setup](docs/PROJECT.md#sip--twilio-setup)

## Demo videos

| Demo | Loom |
|------|------|
| Normal call — appointment booking | [Watch on Loom](https://www.loom.com/share/d5630100730545c58ce3cc7fbd4b3d72) |
| Joining as a watcher (live monitor) | [Watch on Loom](https://www.loom.com/share/e40af8d4bf4344ec8f554cebb91c1c88) |
| Warm transfer — accept & decline | [Watch on Loom](https://www.loom.com/share/7ce3c87d39774840abf1317abff3624c) |

## Demo checklist

- [x] Book appointment conversation — [Loom](https://www.loom.com/share/d5630100730545c58ce3cc7fbd4b3d72)
- [x] Monitor UI updating in real time — [Loom](https://www.loom.com/share/e40af8d4bf4344ec8f554cebb91c1c88)
- [ ] Watcher takeover
- [x] Warm transfer — accept + decline paths — [Loom](https://www.loom.com/share/7ce3c87d39774840abf1317abff3624c)
- [ ] Post-call summary after hangup
