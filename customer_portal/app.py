import math
import os
import re
import sqlite3
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional

import requests
from flask import Flask, g, redirect, render_template, request, url_for, flash

BASE_DIR = os.path.dirname(__file__)
DATABASE = os.path.join(BASE_DIR, "garage_portal.db")
DVLA_API_URL = "https://driver-vehicle-licensing.api.gov.uk/vehicle-enquiry/v1/vehicles"
DVLA_API_KEY = os.getenv("DVLA_API_KEY", "")
LABOUR_RATE = float(os.getenv("LABOUR_RATE", "40"))
VAT_RATE = float(os.getenv("VAT_RATE", "0.20"))
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Samwasbornin20102.")
COMPANY_NAME = os.getenv("COMPANY_NAME", "MGM Prestige")
COMPANY_PHONE = os.getenv("COMPANY_PHONE", "07984 265141")
COMPANY_EMAIL = os.getenv("COMPANY_EMAIL", "ben@mgmprestige.co.uk")
DEFAULT_MAKE = "GENERIC"

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "I LOVE LUCY")


@dataclass
class PartItem:
    sku: str
    name: str
    quantity: float
    unit_price: float
    source: str = "Average manufacturer cost"

    @property
    def total(self) -> float:
        return round(self.quantity * self.unit_price, 2)


MAKE_MULTIPLIERS: Dict[str, float] = {
    "GENERIC": 1.00,
    "BMW": 1.38,
    "MINI": 1.22,
    "AUDI": 1.31,
    "VOLKSWAGEN": 1.15,
    "SKODA": 1.08,
    "SEAT": 1.08,
    "MERCEDES-BENZ": 1.42,
    "MERCEDES": 1.42,
    "FORD": 1.02,
    "VAUXHALL": 0.98,
    "OPEL": 0.98,
    "TOYOTA": 1.05,
    "LEXUS": 1.24,
    "NISSAN": 1.03,
    "HONDA": 1.07,
    "HYUNDAI": 1.01,
    "KIA": 1.00,
    "PEUGEOT": 1.00,
    "CITROEN": 1.00,
    "RENAULT": 1.02,
    "DACIA": 0.92,
    "LAND ROVER": 1.48,
    "JAGUAR": 1.37,
    "VOLVO": 1.24,
    "MAZDA": 1.06,
    "SUZUKI": 0.97,
    "TESLA": 1.18,
}

BASE_PART_COSTS: Dict[str, float] = {
    "oil_filter": 9.50,
    "air_filter": 15.00,
    "pollen_filter": 14.00,
    "spark_plugs_set": 28.00,
    "fuel_filter_petrol": 16.00,
    "fuel_filter_diesel": 24.00,
    "engine_oil_1l": 8.40,
    "sump_washer": 1.50,
    "front_pads": 55.00,
    "front_discs": 95.00,
    "rear_pads": 45.00,
    "rear_discs": 80.00,
    "battery": 110.00,
    "wiper_blades_front_pair": 22.00,
    "wiper_blade_rear": 11.00,
    "brake_fluid_1l": 9.00,
    "coolant_5l": 24.00,
    "timing_belt_kit": 145.00,
    "water_pump": 62.00,
    "aux_belt": 26.00,
    "clutch_kit": 175.00,
    "flywheel": 325.00,
    "gearbox_oil": 28.00,
    "rear_shocks_pair": 115.00,
    "front_shocks_pair": 135.00,
    "front_drop_links_pair": 34.00,
    "front_track_rod_ends_pair": 42.00,
    "rear_pads_only": 45.00,
    "front_pads_only": 55.00,
    "aircon_regas_gas": 68.00,
    "aircon_uv_dye": 7.50,
    "wheel_bearing_front": 74.00,
    "wheel_bearing_rear": 70.00,
    "starter_motor": 140.00,
    "alternator": 210.00,
    "glow_plugs_set": 42.00,
}

JOB_DEFINITIONS: Dict[str, Dict] = {
    "interim_service": {"label": "Interim service", "labour_hours": 0.9, "parts": [
        {"key": "oil_filter", "name": "Oil Filter", "quantity": 1},
        {"key": "engine_oil_1l", "name": "Engine Oil 5W-30", "quantity_from": "oil_litres"},
        {"key": "sump_washer", "name": "Sump Plug Washer", "quantity": 1},
    ]},
    "full_service": {"label": "Full service", "labour_hours": 1.4, "parts": [
        {"key": "oil_filter", "name": "Oil Filter", "quantity": 1},
        {"key": "air_filter", "name": "Air Filter", "quantity": 1},
        {"key": "pollen_filter", "name": "Cabin / Pollen Filter", "quantity": 1},
        {"key": "spark_plugs_set", "name": "Spark Plugs Set", "quantity": 1, "fuel_exclude": ["DIESEL"]},
        {"key": "glow_plugs_set", "name": "Glow Plugs Set", "quantity": 1, "fuel_include": ["DIESEL"]},
        {"key": "fuel_filter_petrol", "name": "Fuel Filter", "quantity": 1, "fuel_exclude": ["DIESEL"]},
        {"key": "fuel_filter_diesel", "name": "Fuel Filter", "quantity": 1, "fuel_include": ["DIESEL"]},
        {"key": "engine_oil_1l", "name": "Engine Oil 5W-30", "quantity_from": "oil_litres"},
        {"key": "sump_washer", "name": "Sump Plug Washer", "quantity": 1},
    ]},
    "major_service": {"label": "Major service", "labour_hours": 1.9, "parts": [
        {"key": "oil_filter", "name": "Oil Filter", "quantity": 1},
        {"key": "air_filter", "name": "Air Filter", "quantity": 1},
        {"key": "pollen_filter", "name": "Cabin / Pollen Filter", "quantity": 1},
        {"key": "spark_plugs_set", "name": "Spark Plugs Set", "quantity": 1, "fuel_exclude": ["DIESEL"]},
        {"key": "glow_plugs_set", "name": "Glow Plugs Set", "quantity": 1, "fuel_include": ["DIESEL"]},
        {"key": "fuel_filter_petrol", "name": "Fuel Filter", "quantity": 1, "fuel_exclude": ["DIESEL"]},
        {"key": "fuel_filter_diesel", "name": "Fuel Filter", "quantity": 1, "fuel_include": ["DIESEL"]},
        {"key": "engine_oil_1l", "name": "Engine Oil 5W-30", "quantity_from": "oil_litres"},
        {"key": "sump_washer", "name": "Sump Plug Washer", "quantity": 1},
        {"key": "brake_fluid_1l", "name": "Brake Fluid 1L", "quantity": 1},
    ]},
    "front_brakes": {"label": "Front brake discs & pads", "labour_hours": 1.2, "parts": [
        {"key": "front_pads", "name": "Front Brake Pads Set", "quantity": 1},
        {"key": "front_discs", "name": "Front Brake Discs Pair", "quantity": 1},
    ]},
    "rear_brakes": {"label": "Rear brake discs & pads", "labour_hours": 1.2, "parts": [
        {"key": "rear_pads", "name": "Rear Brake Pads Set", "quantity": 1},
        {"key": "rear_discs", "name": "Rear Brake Discs Pair", "quantity": 1},
    ]},
    "front_pads_only": {"label": "Front brake pads only", "labour_hours": 0.8, "parts": [{"key": "front_pads_only", "name": "Front Brake Pads Set", "quantity": 1}]},
    "rear_pads_only": {"label": "Rear brake pads only", "labour_hours": 0.8, "parts": [{"key": "rear_pads_only", "name": "Rear Brake Pads Set", "quantity": 1}]},
    "battery_replacement": {"label": "Battery replacement", "labour_hours": 0.35, "parts": [{"key": "battery", "name": "Vehicle Battery", "quantity": 1}]},
    "wiper_blades": {"label": "Wiper blades", "labour_hours": 0.15, "parts": [
        {"key": "wiper_blades_front_pair", "name": "Front Wiper Blades Pair", "quantity": 1},
        {"key": "wiper_blade_rear", "name": "Rear Wiper Blade", "quantity": 1},
    ]},
    "brake_fluid_change": {"label": "Brake fluid change", "labour_hours": 0.7, "parts": [{"key": "brake_fluid_1l", "name": "Brake Fluid 1L", "quantity": 2}]},
    "coolant_change": {"label": "Coolant change", "labour_hours": 1.0, "parts": [{"key": "coolant_5l", "name": "Coolant / Antifreeze 5L", "quantity": 2}]},
    "timing_belt_water_pump": {"label": "Timing belt + water pump", "labour_hours": 4.8, "parts": [
        {"key": "timing_belt_kit", "name": "Timing Belt Kit", "quantity": 1},
        {"key": "water_pump", "name": "Water Pump", "quantity": 1},
        {"key": "coolant_5l", "name": "Coolant / Antifreeze 5L", "quantity": 1},
        {"key": "aux_belt", "name": "Auxiliary Belt", "quantity": 1},
    ]},
    "clutch_replacement": {"label": "Clutch replacement", "labour_hours": 6.5, "parts": [
        {"key": "clutch_kit", "name": "Clutch Kit", "quantity": 1},
        {"key": "gearbox_oil", "name": "Gearbox Oil", "quantity": 1},
    ]},
    "clutch_and_flywheel": {"label": "Clutch + dual mass flywheel", "labour_hours": 7.2, "parts": [
        {"key": "clutch_kit", "name": "Clutch Kit", "quantity": 1},
        {"key": "flywheel", "name": "Dual Mass Flywheel", "quantity": 1},
        {"key": "gearbox_oil", "name": "Gearbox Oil", "quantity": 1},
    ]},
    "rear_shocks": {"label": "Rear shock absorbers", "labour_hours": 1.4, "parts": [{"key": "rear_shocks_pair", "name": "Rear Shock Absorbers Pair", "quantity": 1}]},
    "front_shocks": {"label": "Front shock absorbers", "labour_hours": 2.6, "parts": [{"key": "front_shocks_pair", "name": "Front Shock Absorbers Pair", "quantity": 1}]},
    "drop_links": {"label": "Front drop links", "labour_hours": 0.9, "parts": [{"key": "front_drop_links_pair", "name": "Front Drop Links Pair", "quantity": 1}]},
    "track_rod_ends": {"label": "Track rod ends", "labour_hours": 1.1, "parts": [{"key": "front_track_rod_ends_pair", "name": "Track Rod Ends Pair", "quantity": 1}]},
    "aircon_regas": {"label": "Air conditioning regas", "labour_hours": 0.8, "parts": [
        {"key": "aircon_regas_gas", "name": "A/C Gas", "quantity": 1},
        {"key": "aircon_uv_dye", "name": "UV Dye", "quantity": 1},
    ]},
    "front_wheel_bearing": {"label": "Front wheel bearing", "labour_hours": 1.8, "parts": [{"key": "wheel_bearing_front", "name": "Front Wheel Bearing", "quantity": 1}]},
    "rear_wheel_bearing": {"label": "Rear wheel bearing", "labour_hours": 1.6, "parts": [{"key": "wheel_bearing_rear", "name": "Rear Wheel Bearing", "quantity": 1}]},
    "starter_motor": {"label": "Starter motor replacement", "labour_hours": 1.6, "parts": [{"key": "starter_motor", "name": "Starter Motor", "quantity": 1}]},
    "alternator": {"label": "Alternator replacement", "labour_hours": 1.7, "parts": [{"key": "alternator", "name": "Alternator", "quantity": 1}]},
}


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@app.template_filter("money")
def money_filter(value):
    return f"£{float(value):,.2f}"


@app.template_filter("qty")
def qty_filter(value):
    return str(int(value)) if float(value).is_integer() else f"{float(value):.1f}"


def init_db():
    db = sqlite3.connect(DATABASE)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS booking_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quote_ref TEXT NOT NULL,
            created_at TEXT NOT NULL,
            registration TEXT NOT NULL,
            vehicle_make TEXT,
            vehicle_model TEXT,
            vehicle_year TEXT,
            fuel_type TEXT,
            engine_capacity TEXT,
            job_code TEXT NOT NULL,
            job_label TEXT NOT NULL,
            quoted_total REAL NOT NULL,
            customer_name TEXT NOT NULL,
            customer_email TEXT NOT NULL,
            customer_phone TEXT NOT NULL,
            preferred_date TEXT,
            preferred_time TEXT,
            notes TEXT,
            status TEXT NOT NULL DEFAULT 'new'
        );
        """
    )
    db.commit()
    db.close()


def normalize_registration(registration: str) -> str:
    return re.sub(r"\s+", "", (registration or "").strip().upper())


def get_make_multiplier(make: Optional[str]) -> float:
    if not make:
        return MAKE_MULTIPLIERS[DEFAULT_MAKE]
    return MAKE_MULTIPLIERS.get(make.upper(), MAKE_MULTIPLIERS[DEFAULT_MAKE])


def estimate_oil_litres(engine_capacity: Optional[int]) -> float:
    try:
        cc = int(engine_capacity or 0)
    except (TypeError, ValueError):
        cc = 0
    if cc <= 0:
        return 5.0
    if cc <= 1400:
        return 4.0
    if cc <= 1800:
        return 4.5
    if cc <= 2200:
        return 5.0
    if cc <= 3000:
        return 6.0
    return 7.0


def fetch_vehicle_data(registration: str) -> Dict:
    reg = normalize_registration(registration)
    if not reg:
        raise ValueError("Please enter a registration.")
    if DVLA_API_KEY:
        try:
            response = requests.post(
                DVLA_API_URL,
                headers={"x-api-key": DVLA_API_KEY, "Content-Type": "application/json"},
                json={"registrationNumber": reg},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            data["registrationNumber"] = reg
            return data
        except Exception as exc:
            return demo_vehicle_data(reg, notice=f"DVLA lookup failed, so demo vehicle data is shown for testing. ({exc})")
    return demo_vehicle_data(reg, notice="DVLA key not configured, so demo vehicle data is shown for testing.")


def demo_vehicle_data(registration: str, notice: str) -> Dict:
    prefix = registration[:2]
    seeded = {
        "registrationNumber": registration,
        "make": "BMW" if prefix in {"BK", "BM", "BX"} else "FORD" if prefix in {"FN", "FY", "FX"} else "VOLKSWAGEN",
        "model": "Demo vehicle",
        "fuelType": "DIESEL" if registration[-1:].isdigit() else "PETROL",
        "yearOfManufacture": 2018,
        "engineCapacity": 1995,
        "motStatus": "No details held",
        "taxStatus": "Taxed",
        "_notice": notice,
    }
    return seeded


def build_parts(job_code: str, vehicle: Dict) -> List[PartItem]:
    definition = JOB_DEFINITIONS[job_code]
    fuel = (vehicle.get("fuelType") or "").upper()
    oil_litres = estimate_oil_litres(vehicle.get("engineCapacity"))
    multiplier = get_make_multiplier(vehicle.get("make"))

    items: List[PartItem] = []
    for spec in definition["parts"]:
        include = spec.get("fuel_include")
        exclude = spec.get("fuel_exclude")
        if include and fuel not in include:
            continue
        if exclude and fuel in exclude:
            continue
        quantity = spec.get("quantity", 1)
        if "quantity_from" in spec and spec["quantity_from"] == "oil_litres":
            quantity = oil_litres
        base = BASE_PART_COSTS[spec["key"]]
        unit_price = round(base * multiplier, 2)
        items.append(
            PartItem(
                sku=spec["key"].upper(),
                name=spec["name"],
                quantity=float(quantity),
                unit_price=unit_price,
                source=f"Average {vehicle.get('make') or 'manufacturer'} cost",
            )
        )
    return items


def calculate_quote(job_code: str, vehicle: Dict) -> Dict:
    parts = build_parts(job_code, vehicle)
    labour_hours = JOB_DEFINITIONS[job_code]["labour_hours"]
    parts_total = round(sum(item.total for item in parts), 2)
    labour_total = round(labour_hours * LABOUR_RATE, 2)
    subtotal = round(parts_total + labour_total, 2)
    vat = round(subtotal * VAT_RATE, 2)
    grand_total = round(subtotal + vat, 2)
    totals = {
        "oil_litres": estimate_oil_litres(vehicle.get("engineCapacity")),
        "parts_total": parts_total,
        "labour_hours": labour_hours,
        "labour_rate": LABOUR_RATE,
        "labour_total": labour_total,
        "subtotal": subtotal,
        "vat": vat,
        "grand_total": grand_total,
    }
    return {"parts": parts, "totals": totals}


def services_list() -> List:
    return [(code, details["label"]) for code, details in JOB_DEFINITIONS.items()]


def make_quote_ref() -> str:
    return f"Q-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


@app.context_processor
def inject_globals():
    return {
        "company_name": COMPANY_NAME,
        "company_phone": COMPANY_PHONE,
        "company_email": COMPANY_EMAIL,
        "pricing_basis": "average manufacturer parts costs with fixed labour matrix",
        "services": services_list(),
    }


@app.route("/", methods=["GET", "POST"])
def home():
    context = {
        "entered_reg": "",
        "selected_job": "full_service",
        "vehicle": None,
        "parts": [],
        "totals": None,
        "job_label": None,
        "error": None,
        "quote_ref": None,
    }
    if request.method == "POST":
        reg = request.form.get("registration", "")
        job_code = request.form.get("job_code", "full_service")
        context["entered_reg"] = reg
        context["selected_job"] = job_code
        try:
            if job_code not in JOB_DEFINITIONS:
                raise ValueError("Please choose a valid service or repair.")
            vehicle = fetch_vehicle_data(reg)
            quote = calculate_quote(job_code, vehicle)
            context.update(
                {
                    "vehicle": vehicle,
                    "parts": quote["parts"],
                    "totals": quote["totals"],
                    "job_label": JOB_DEFINITIONS[job_code]["label"],
                    "quote_ref": make_quote_ref(),
                }
            )
        except Exception as exc:
            context["error"] = str(exc)
    return render_template("index.html", **context)


@app.route("/book", methods=["POST"])
def book():
    reg = request.form.get("registration", "")
    job_code = request.form.get("job_code", "")
    name = request.form.get("customer_name", "").strip()
    email = request.form.get("customer_email", "").strip()
    phone = request.form.get("customer_phone", "").strip()
    preferred_date = request.form.get("preferred_date", "").strip()
    preferred_time = request.form.get("preferred_time", "").strip()
    notes = request.form.get("notes", "").strip()
    quote_ref = request.form.get("quote_ref", make_quote_ref())

    if not all([name, email, phone, reg, job_code]):
        flash("Please complete name, email, phone, registration and selected job.")
        return redirect(url_for("home"))
    if job_code not in JOB_DEFINITIONS:
        flash("Invalid job selected.")
        return redirect(url_for("home"))

    vehicle = fetch_vehicle_data(reg)
    quote = calculate_quote(job_code, vehicle)

    db = get_db()
    db.execute(
        """
        INSERT INTO booking_requests (
            quote_ref, created_at, registration, vehicle_make, vehicle_model, vehicle_year,
            fuel_type, engine_capacity, job_code, job_label, quoted_total,
            customer_name, customer_email, customer_phone, preferred_date, preferred_time, notes, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')
        """,
        (
            quote_ref,
            datetime.utcnow().isoformat(timespec="seconds"),
            normalize_registration(reg),
            vehicle.get("make"),
            vehicle.get("model"),
            str(vehicle.get("yearOfManufacture") or ""),
            vehicle.get("fuelType"),
            str(vehicle.get("engineCapacity") or ""),
            job_code,
            JOB_DEFINITIONS[job_code]["label"],
            quote["totals"]["grand_total"],
            name,
            email,
            phone,
            preferred_date,
            preferred_time,
            notes,
        ),
    )
    db.commit()
    return render_template(
        "booking_success.html",
        quote_ref=quote_ref,
        customer_name=name,
        registration=normalize_registration(reg),
        quoted_total=quote["totals"]["grand_total"],
        preferred_date=preferred_date,
        preferred_time=preferred_time,
        job_label=JOB_DEFINITIONS[job_code]["label"],
    )


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        if request.form.get("password") != ADMIN_PASSWORD:
            return render_template("admin_login.html", error="Wrong password."), 403
        db = get_db()
        bookings = db.execute("SELECT * FROM booking_requests ORDER BY id DESC").fetchall()
        return render_template("admin_bookings.html", bookings=bookings)
    return render_template("admin_login.html", error=None)


@app.route("/health")
def health():
    return {"ok": True, "service": "garage-customer-portal"}


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5001")), debug=True)
