# QueryIQ — Enterprise AI Data Analytics Platform

> Natural-language analytics over your data, powered by LLMs.

## 🚀 Quick Start (Development)

### Prerequisites
- Python 3.11+
- Node.js 20+
- [Ollama](https://ollama.ai) running locally with a model pulled

```bash
# Pull a model (e.g. qwen2.5:3b)
ollama pull qwen2.5:3b
```

### 1. Clone & Setup Environment
```bash
git clone <repo-url>
cd queryiq

# Copy env template and fill in your values
cp .env.example .env
```

### 2. Backend
```bash
# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate    # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Run the backend
uvicorn backend.main:app --reload --port 8000
```

### 3. Frontend
```bash
cd nexus-ai-studio

# Install dependencies
npm install

# Run dev server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## 🐳 Production Deployment (Docker)

### Prerequisites
- Docker & Docker Compose
- A domain name with DNS pointing to your server

### 1. Configure Environment
```bash
# Copy and fill in ALL required values
cp .env.example .env
nano .env
```

**Required production variables:**
```bash
ENVIRONMENT=production

# Generate with: python -c "import secrets; print(secrets.token_hex(64))"
JWT_SECRET=<your-64-char-hex-secret>
JWT_REFRESH_SECRET=<your-64-char-hex-secret>

# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FERNET_KEY=<your-fernet-key>

# PostgreSQL
DATABASE_URL=postgresql://queryiq:yourpassword@postgres:5432/queryiq_db
POSTGRES_USER=queryiq
POSTGRES_PASSWORD=<strong-password>

# Your production frontend domain
FRONTEND_URL=https://your-domain.com
ALLOWED_HOSTS=your-domain.com,www.your-domain.com

# Your production API URL (used at build time for frontend)
FRONTEND_API_URL=https://your-domain.com
```

### 2. Configure Nginx
Edit `nginx.conf` and replace `your-domain.com` with your actual domain.

### 3. Build & Launch
```bash
docker-compose up --build -d
```

### 4. Verify
```bash
# Check all containers are healthy
docker-compose ps

# Check backend health
curl https://your-domain.com/api/health
```

---

## 🔐 Security Checklist

Before going live, verify:

- [ ] `JWT_SECRET` is a random 64-char hex string (not the default)
- [ ] `JWT_REFRESH_SECRET` is a different random 64-char hex string
- [ ] `FERNET_KEY` is set and backed up securely
- [ ] `ENVIRONMENT=production` is set in `.env`
- [ ] `DATABASE_URL` points to PostgreSQL (not SQLite)
- [ ] `FRONTEND_URL` is your real domain (not localhost)
- [ ] `ALLOWED_HOSTS` lists only your domain
- [ ] SSL certificates are configured in `nginx.conf`
- [ ] `/docs` and `/redoc` endpoints are blocked in nginx (uncomment in nginx.conf)
- [ ] The `.env` file is **never committed** to git

---

## 📁 Project Structure

```
queryiq/
├── backend/               # FastAPI Python backend
│   ├── main.py            # App entry point, middleware, routers
│   ├── config.py          # Centralized config from .env
│   ├── routers/           # API route handlers (21 routers)
│   ├── services/          # Business logic (42 services)
│   ├── models/            # Pydantic schemas
│   ├── prompts/           # LLM prompt templates
│   └── tests/             # Test suite
├── nexus-ai-studio/       # Next.js TypeScript frontend
│   ├── src/app/           # Page routes (7 pages)
│   └── src/components/    # Reusable UI components
├── data/                  # Runtime data (gitignored)
├── docker-compose.yml     # Full stack orchestration
├── nginx.conf             # Reverse proxy config
├── requirements.txt       # Python dependencies (pinned)
└── .env.example           # Environment variable template
```

---

## 🧪 Running Tests

```bash
# From project root, with venv activated
pytest backend/tests/ -v

# Stress tests
python backend/tests/run_stress_tests.py

# Enterprise benchmarks
python backend/tests/run_enterprise_benchmarks.py
```

---

## 📊 Health Monitoring

The backend exposes a health endpoint:
```
GET /api/health
```

Response includes: backend status, LLM connectivity, dataset count, uptime, model availability.

---

## ⚙️ Configuration Reference

All configuration is read from `.env`. See [.env.example](.env.example) for the complete list with descriptions.

| Variable | Required in Prod | Default | Description |
|---|---|---|---|
| `ENVIRONMENT` | ✅ | `development` | Set to `production` to enable strict mode |
| `JWT_SECRET` | ✅ | (dev fallback) | JWT signing secret — must be strong in prod |
| `JWT_REFRESH_SECRET` | ✅ | (dev fallback) | Refresh token signing secret |
| `FERNET_KEY` | ✅ | (auto-generated) | Encryption key for DB credentials |
| `DATABASE_URL` | ✅ | SQLite | PostgreSQL URL for production |
| `FRONTEND_URL` | ✅ | localhost:3000 | CORS allowed origin |
| `ALLOWED_HOSTS` | ✅ | localhost | Trusted Host middleware |
| `GEMINI_API_KEY` | ❌ | None | Enables Google Gemini LLM |
| `OLLAMA_BASE_URL` | ❌ | localhost:11434 | Local Ollama endpoint |
| `DEFAULT_MODEL` | ❌ | qwen2.5:3b | Default LLM model |
