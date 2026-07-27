# QueryMind — Week 1 Setup

## 1. Start the infra stack

```bash
docker compose up -d
```

Check everything is healthy:

```bash
docker compose ps
```

You should see `postgres`, `mysql`, `redis`, `kafka`, and `kafka-ui` all running.

- Postgres → `localhost:5432` (user: `querymind` / pass: `querymind_dev_pw` / db: `querymind`)
- MySQL → `localhost:3306` (user: `querymind` / pass: `querymind_dev_pw` / db: `querymind_sample`)
- Redis → `localhost:6379`
- Kafka → `localhost:9092`
- Kafka UI (browser) → http://localhost:8080

## 2. Set up the Python environment

```bash
cd backend
python -m venv .venv

# Windows:
.venv\Scripts\activate
# Mac/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

## 3. Run the scaffold API

```bash
uvicorn main:app --reload --port 8000
```

Then check in browser or curl:

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status": "ok", "service": "querymind-scaffold", "timestamp": "..."}
```

## Week 1 checklist

- [ ] `docker compose up -d` brings up all 5 containers with no errors
- [ ] `docker compose ps` shows all as healthy
- [ ] Kafka UI loads at localhost:8080 and shows the cluster (no topics yet — that's expected)
- [ ] Python venv created, dependencies installed
- [ ] `GET /health` returns 200 with a timestamp
- [ ] Connect to Postgres via DBeaver using the credentials above, confirm you can browse it
- [ ] `git add . && git commit -m "Week 1: environment + scaffold"` and push to GitHub

Once all boxes are checked, you're ready for Phase 2 (Schema Service).
