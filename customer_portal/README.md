# Garage customer quote and booking portal

This version is set up for customer-facing use and deployment on Render or Railway.

## Features
- Registration-based quote flow
- Vehicle verification panel
- Average manufacturer parts costs by make
- Labour, VAT, and total quote summary
- Customer booking request form
- SQLite booking storage
- Basic admin bookings screen at `/admin`
- Render deploy file included

## Important current limitation
This build does **not** use a live Euro Car Parts API because I could not verify a public ECP pricing API suitable for direct integration. It currently uses average manufacturer parts costs by make. DVLA lookup can be enabled with your own API key.

## Local run
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
Open `http://127.0.0.1:5001`

## Environment variables
- `DVLA_API_KEY` = your DVLA Vehicle Enquiry Service key
- `ADMIN_PASSWORD` = password for `/admin`
- `FLASK_SECRET_KEY` = random secret for production
- `LABOUR_RATE` = hourly labour rate, default 78
- `VAT_RATE` = default 0.20
- `COMPANY_NAME`, `COMPANY_PHONE`, `COMPANY_EMAIL`

## Deploy to Render
1. Push this folder to GitHub.
2. In Render, create a new Web Service from the repo.
3. Render can use `render.yaml` automatically, or set:
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app`
4. Add environment variables in Render dashboard.
5. After first deploy, visit `/admin` and sign in with `ADMIN_PASSWORD`.

## Deploy to Railway
- New Project -> Deploy from GitHub repo
- Railway will detect Python from `requirements.txt`
- Start command: `gunicorn app:app`
- Add the same environment variables in the project settings

## Next sensible upgrades
- real supplier API or approved feed
- diary slot management instead of preferred-date capture only
- email notifications to garage and customer
- online deposit / Stripe checkout
- customer quote PDFs
- better admin authentication
