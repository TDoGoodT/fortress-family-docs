# Fortress — Deployment Checklist

## Prerequisites
- [ ] Mac Mini with Docker (OrbStack)
- [ ] Git installed
- [ ] AWS credentials (Access Key + Secret Key)
- [ ] Fortress phone with SIM

## Steps
1. Clone: `git clone https://github.com/Segway16/fortress-family.git`
2. Navigate: `cd fortress-family/fortress`
3. Create .env: `cp .env.example .env` → edit with real values
4. Create seed: `cp scripts/seed_family.sh.template scripts/seed_family.sh` → edit
5. Build: `docker compose up -d --build`
6. Wait: `sleep 20`
7. Migrations: run all .sql files in order
8. Seed: run seed_family.sh
9. Health: `curl http://localhost:8000/health`
10. WAHA: open http://localhost:3000, scan QR
11. Test: send "שלום" from phone
12. Dashboard: open http://localhost:8000/dashboard

## Post-Deploy Verification
- [ ] Health returns all services connected
- [ ] "שלום" returns personalized greeting
- [ ] "משימה חדשה: טסט" creates task
- [ ] "משימות" shows the task
- [ ] "מחק משימה 1" → confirm → deleted
- [ ] Photo upload → "שמרתי ✅" + classification
- [ ] "מסמכים" shows the upload
- [ ] "עזרה" shows skill list
- [ ] "באג: test" creates bug report
- [ ] Dashboard shows activity
