# SwadesAI — Voice Agent Hackathon

Conversational voice agent with **appointment booking**, **live monitoring**, **watcher takeover**, and **warm transfer** to a human via Twilio SIP.

Built with **Python (LiveKit Agents)**, **Next.js**, **Groq**, **Deepgram / Sarvam AI**, and **LiveKit Cloud**.

## Architecture

```
Caller (phone or browser) → LiveKit Room ← Python Agent A (STT → LLM → TTS)
                                    ↑
                         Next.js Monitor (transcript, state, takeover)
                                    ↓
                    Warm Transfer → Supervisor phone (Twilio SIP outbound)
```

## Prerequisites

1. [LiveKit Cloud](https://cloud.livekit.io) account (free tier)
2. [Groq](https://console.groq.com) API key (free tier)
3. [Deepgram](https://console.deepgram.com) API key
4. [Twilio](https://twilio.com) account with SIP trunk configured for LiveKit ([SIP guide](https://docs.livekit.io/sip/quickstarts/configuring-sip-trunk/))
5. Python 3.10+, Node.js 18+

## Setup

### 1. Environment variables

```bash
cp .env.example .env
cp frontend/.env.local.example frontend/.env.local
```

Fill in both files with your keys. The backend reads `.env` from the repo root (or `backend/` if you copy it there).

| Variable | Purpose |
|----------|---------|
| `LIVEKIT_URL` | WebSocket URL from LiveKit Cloud |
| `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` | Server API credentials |
| `GROQ_API_KEY` | LLM + post-call summary (free tier at console.groq.com) |
| `GROQ_MODEL` | Optional; defaults to `llama-3.1-8b-instant` |
| `DEEPGRAM_API_KEY` | English STT/TTS (when `AGENT_LANGUAGE=en`) |
| `SARVAM_API_KEY` | Malayalam STT/TTS via [Sarvam AI](https://www.sarvam.ai) (when `AGENT_LANGUAGE=ml`) |
| `AGENT_LANGUAGE` | `en` (Deepgram) or `ml` / `malayalam` (Sarvam Bulbul TTS + Saarika STT) |
| `LIVEKIT_SIP_OUTBOUND_TRUNK` | **Outbound** SIP trunk ID for warm transfer (not the inbound trunk) |
| `LIVEKIT_SUPERVISOR_PHONE_NUMBER` | Human agent phone (E.164) |
| `LIVEKIT_SIP_NUMBER` | Caller ID shown to supervisor |
| `INBOUND_PHONE_NUMBER` / `NEXT_PUBLIC_INBOUND_PHONE_NUMBER` | Your Twilio inbound number |
| `AGENT_NAME` | Must match `swades-agent` in code |

### 2. SIP / Twilio (phone calls)

1. Create **inbound** SIP trunk in LiveKit pointing to Twilio
2. Create **dispatch rule** → agent name `swades-agent` (matches `AGENT_NAME`)
3. Create **outbound** SIP trunk for warm transfer
4. Assign your Twilio number to the inbound trunk
5. **Twilio trial accounts:** verify the supervisor phone in [Verified Caller IDs](https://console.twilio.com/us1/develop/phone-numbers/manage/verified) — trial accounts can only dial verified numbers (error `32100`)

See [LiveKit warm-transfer example](https://github.com/livekit/agents/tree/main/examples/warm-transfer).

### 3. Backend (Python agent)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python agent.py dev
```

Local console test (no LiveKit room):

```bash
python agent.py console
```

### 4. Frontend (Next.js)

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Flows

### Booking (Agent A)

1. Caller provides name, reason, preferred date/time, phone
2. Agent calls `check_availability` tool
3. Caller picks a slot → agent calls `book_appointment`
4. Agent reads confirmation aloud
5. Appointments stored in `backend/data/appointments.db` (SQLite)

### Live monitoring

1. Open **Monitor Dashboard** (`/monitor`)
2. Enter the room name (shown during web call, or from LiveKit dashboard for SIP calls)
3. Click **Join as Watcher**
4. See live transcript, agent state (listening/thinking/speaking), intent, and action

### Watcher takeover

1. From monitor dashboard, click **Take Over**
2. Agent audio pauses; watcher mic is enabled
3. Watcher speaks directly to caller
4. **Release to Agent** returns control to Agent A

### Warm transfer

1. Caller asks for a human (billing, complaint, etc.)
2. Agent confirms, then calls `transfer_to_human`
3. Caller placed on hold; supervisor dialed via Twilio SIP
4. Agent briefs supervisor; on accept → caller connected to human
5. On decline/no answer → agent returns and apologizes

### Post-call summary

When the session ends, OpenAI generates a bullet summary saved to SQLite and shown in the monitor UI.

## Project structure

```
backend/
  agent.py       # Main voice agent + tools + takeover handler
  booking.py     # SQLite appointments
  monitor.py     # Publishes events to data channel
  summary.py     # Post-call LLM summary
frontend/
  src/app/call/       # Start web call with Agent A
  src/app/monitor/    # Watcher dashboard
  src/app/api/token/  # LiveKit JWT + agent dispatch
  src/components/     # VoiceRoom, transcript, state panels
```

## Demo recording checklist (Loom)

- [ ] Book appointment conversation (phone or web)
- [ ] Monitor UI updating in real time
- [ ] Watcher takeover mid-call
- [ ] Warm transfer — supervisor accepts
- [ ] Warm transfer — supervisor declines / unavailable
- [ ] Post-call summary visible after hangup

## Push to GitHub

```bash
git init
git add .
git commit -m "Initial SwadesAI voice agent hackathon project"
git remote add origin https://github.com/YOUR_USER/swadesAI.git
git push -u origin main
```
