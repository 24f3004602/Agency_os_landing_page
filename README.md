# Agency OS — Development Setup

## Architecture

```
DEV MACHINE (you code here)          HOMELAB (Tailscale)
──────────────────────────           ──────────────────────────────
FastAPI  :8000                        PostgreSQL  :5432  (existing)
Celery worker                         n8n         :5678  (existing)
React/Vite :5173                      Redis       :6379  (NEW)
                                      Qdrant      :6333  (NEW)
                                      Ollama      :11434 (NEW)
```

---

## Step 1 — Homelab: Add Agency OS database

SSH into your homelab and run:

```bash
# Connect to your existing Postgres container
docker exec -it <your_postgres_container> psql -U postgres

# Inside psql:
CREATE USER agencyos WITH PASSWORD 'agencyos_password';
CREATE DATABASE agencyos OWNER agencyos;
GRANT ALL PRIVILEGES ON DATABASE agencyos TO agencyos;
\q
```

---

## Step 2 — Homelab: Start new services

```bash
cd agencyos/infra
docker compose -f docker-compose.homelab.yml up -d

# Pull the embedding model (one-time, ~270MB)
docker exec agencyos_ollama ollama pull nomic-embed-text

# Verify
docker exec agencyos_ollama ollama list
# Should show: nomic-embed-text
```

---

## Step 3 — Dev machine: Backend setup

```bash
cd agencyos/backend

# Create virtualenv
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# Install deps
pip install -r requirements.txt

# Copy env and fill in your Tailscale IPs
cp .env.example .env
# Edit .env — replace 100.x.x.x with your homelab's Tailscale IP

# Run initial migration
alembic revision --autogenerate -m "initial schema"
alembic upgrade head

# Start FastAPI
uvicorn app.main:app --reload --port 8000
```

Visit http://localhost:8000/docs — you should see the Swagger UI.

---

## Step 4 — Dev machine: Start Celery worker

```bash
# In a separate terminal, same virtualenv
cd agencyos/backend
source venv/bin/activate
celery -A celery_worker.celery_app worker --loglevel=info -Q m1,m2,agents,default
```

---

## Step 5 — Dev machine: Frontend setup

```bash
cd agencyos/frontend
npm install
npm run dev
```

Visit http://localhost:5173

---

## Step 6 — Test login

SuperAdmin login:
- Email: whatever you set as SUPERADMIN_EMAIL in .env
- Password: whatever you set as SUPERADMIN_PASSWORD

You should land on `/superadmin` after login.

---

## Step 7 — n8n Tailscale setup

In n8n (on homelab), when creating webhooks that call FastAPI:
- Use your DEV MACHINE's Tailscale IP: `http://100.YOUR.DEV.IP:8000/api/v1/...`
- Make sure your dev machine firewall allows port 8000 from Tailscale interface

```bash
# On dev machine — allow Tailscale traffic to port 8000
sudo ufw allow in on tailscale0 to any port 8000
```

---

## Module build order

| Phase | What we build |
|-------|--------------|
| ✅ 0  | Scaffold, auth, DB, Celery |
| 1     | M1: Attendance schema + geofence API |
| 2     | M1: Task dispatch + Celery deadline monitor |
| 3     | M1: Payroll + WeasyPrint payslips |
| 4     | M1: Communication logging (Gmail + WATI) |
| 5     | M1: EOM Scoring Agent (LangGraph) |
| 6     | M2: Onboarding Agent + Invoice generation |
| 7     | Frontend: Employee Dashboard |
| 8     | Frontend: Owner Dashboard |

---

## Useful commands

```bash
# New migration after model change
alembic revision --autogenerate -m "describe change"
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Celery beat scheduler (for scheduled agents)
celery -A celery_worker.celery_app beat --loglevel=info

# Check Qdrant collections
curl http://100.x.x.x:6333/collections

# Test Ollama embedding
curl http://100.x.x.x:11434/api/embeddings \
  -d '{"model":"nomic-embed-text","prompt":"test"}'
```
