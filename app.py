import sqlite3
from functools import wraps
from pathlib import Path
import json
import os
from werkzeug.utils import secure_filename

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, g
import firebase_admin
from firebase_admin import credentials, auth as firebase_auth
from placements_fetcher import get_placements
from internships_fetcher import get_all_internships
from gemini_recommender import get_gemini_recommendations, get_gemini_api_key

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = "268bc7bb5a78de350d0280331af78a7a23d4cf671458b37f2816036503c71115"

DB_PATH = Path(__file__).parent / "nsb.db"
RESUME_UPLOAD_FOLDER = Path(__file__).parent / "static" / "uploads" / "resumes"
RESUME_UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

# Point this at the service account JSON from Firebase console
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)


# ---------------------------------------------------------------------------
# Database helpers (plain sqlite3)
# ---------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS profiles (
            uid TEXT PRIMARY KEY,
            email TEXT,
            name TEXT,
            phone TEXT,
            gender TEXT,
            state_city TEXT,
            degree TEXT,
            field_of_study TEXT,
            graduation_year TEXT,
            cgpa_percentage TEXT,
            skills TEXT,
            primary_skills TEXT,
            soft_skills TEXT,
            experience_level TEXT,
            preferred_sectors TEXT,
            location TEXT,
            preferred_locations TEXT,
            internship_mode TEXT,
            availability TEXT,
            resume_url TEXT,
            resume_pdf TEXT
        )
        """
    )
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "uid" not in session:
            return redirect(url_for("login_page"))
        return view(*args, **kwargs)
    return wrapped


def get_profile(uid):
    db = get_db()
    row = db.execute("SELECT * FROM profiles WHERE uid = ?", (uid,)).fetchone()
    if not row:
        return None
    d = dict(row)
    for k, v in d.items():
        if v is None:
            d[k] = ""
    return d


def upsert_profile(uid, **fields):
    db = get_db()
    existing = get_profile(uid)
    if existing:
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        db.execute(
            f"UPDATE profiles SET {set_clause} WHERE uid = ?",
            (*fields.values(), uid),
        )
    else:
        columns = ", ".join(["uid", *fields.keys()])
        placeholders = ", ".join(["?"] * (len(fields) + 1))
        db.execute(
            f"INSERT INTO profiles ({columns}) VALUES ({placeholders})",
            (uid, *fields.values()),
        )
    db.commit()


# ---------------------------------------------------------------------------
# Auth routes (Google Authentication)
# ---------------------------------------------------------------------------
@app.route("/login")
def login_page():
    return render_template("login.html")


@app.route("/api/session", methods=["POST"])
def create_session():
    """Called by frontend after Firebase Google Sign-In.
    Verifies ID token and initiates Flask session."""
    id_token = request.json.get("idToken") if request.is_json else None
    if not id_token:
        return jsonify({"error": "Missing idToken"}), 400

    try:
        decoded = firebase_auth.verify_id_token(id_token)
    except Exception:
        return jsonify({"error": "Invalid or expired token"}), 401

    uid = decoded["uid"]
    email = decoded.get("email", "")
    name = decoded.get("name", "")

    session["uid"] = uid
    session["email"] = email

    existing = get_profile(uid)
    if not existing:
        upsert_profile(
            uid,
            email=email,
            name=name,
            phone="",
            gender="Other",
            state_city="",
            degree="",
            field_of_study="",
            graduation_year="2026",
            cgpa_percentage="",
            skills="",
            primary_skills="",
            soft_skills="",
            experience_level="Fresher",
            preferred_sectors="",
            location="Any",
            preferred_locations="Any",
            internship_mode="Hybrid",
            availability="Immediate (Full-time)",
            resume_url=""
        )
        # New candidate signup -> redirect to profile setup onboarding
        return jsonify({"redirect": url_for("profile_page")})
    elif not existing.get("degree") or not (existing.get("skills") or existing.get("primary_skills")):
        # Incomplete profile -> redirect to profile setup onboarding
        return jsonify({"redirect": url_for("profile_page")})

    return jsonify({"redirect": url_for("home")})


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# ---------------------------------------------------------------------------
# App routes (all require login)
# ---------------------------------------------------------------------------
@app.route("/")
@login_required
def home():
    profile = get_profile(session["uid"]) or {}
    return render_template("index.html", profile=profile)


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile_page():
    uid = session["uid"]
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        gender = request.form.get("gender", "Other").strip()
        state_city = request.form.get("state_city", "").strip()
        degree = request.form.get("degree", "").strip()
        field_of_study = request.form.get("field_of_study", "").strip()
        graduation_year = request.form.get("graduation_year", "2026").strip()
        cgpa_percentage = request.form.get("cgpa_percentage", "").strip()
        skills = request.form.get("skills", "").strip()
        soft_skills = request.form.get("soft_skills", "").strip()
        experience_level = request.form.get("experience_level", "Fresher").strip()
        preferred_sectors = request.form.get("preferred_sectors", "").strip()
        location = request.form.get("location", "Any").strip()
        internship_mode = request.form.get("internship_mode", "Hybrid").strip()
        availability = request.form.get("availability", "Immediate (Full-time)").strip()
        resume_url = request.form.get("resume_url", "").strip()

        resume_pdf_file = request.files.get("resume_pdf")
        resume_pdf_name = None
        if resume_pdf_file and resume_pdf_file.filename:
            if resume_pdf_file.filename.lower().endswith(".pdf"):
                safe_name = secure_filename(resume_pdf_file.filename)
                stored_name = f"{uid}_{safe_name}"
                resume_pdf_file.save(RESUME_UPLOAD_FOLDER / stored_name)
                resume_pdf_name = safe_name

        try:
            profile_data = {
                "email": session.get("email", ""),
                "name": name,
                "phone": phone,
                "gender": gender,
                "state_city": state_city,
                "degree": degree,
                "field_of_study": field_of_study,
                "graduation_year": graduation_year,
                "cgpa_percentage": cgpa_percentage,
                "skills": skills,
                "primary_skills": skills,
                "soft_skills": soft_skills,
                "experience_level": experience_level,
                "preferred_sectors": preferred_sectors,
                "location": location,
                "preferred_locations": location,
                "internship_mode": internship_mode,
                "availability": availability,
                "resume_url": resume_url
            }
            if resume_pdf_name:
                profile_data["resume_pdf"] = resume_pdf_name

            upsert_profile(uid, **profile_data)
            return redirect(url_for("home", status="saved"))
        except Exception as e:
            print("Error saving profile:", e)
            return redirect(url_for("home", status="error"))

    profile = get_profile(uid) or {}
    return render_template("profile.html", profile=profile, saved=False)


@app.route("/api/upload_resume", methods=["POST"])
@login_required
def upload_resume_api():
    uid = session["uid"]
    if "resume_pdf" not in request.files:
        return jsonify({"error": "No file part in request"}), 400
    
    file = request.files["resume_pdf"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400
    
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are supported"}), 400

    safe_name = secure_filename(file.filename)
    stored_name = f"{uid}_{safe_name}"
    file.save(RESUME_UPLOAD_FOLDER / stored_name)
    upsert_profile(uid, resume_pdf=safe_name)

    return jsonify({
        "status": "uploaded",
        "filename": safe_name,
        "size": os.path.getsize(RESUME_UPLOAD_FOLDER / stored_name)
    })


@app.route("/courses")
@login_required
def courses():
    profile = get_profile(session["uid"]) or {}
    software_dir = Path(__file__).parent / "static" / "courses" / "software"
    hardware_dir = Path(__file__).parent / "static" / "courses" / "hardware"
    software_dir.mkdir(parents=True, exist_ok=True)
    hardware_dir.mkdir(parents=True, exist_ok=True)

    def scan_pdfs(folder_path, category_name):
        pdf_list = []
        for p in folder_path.glob("*.pdf"):
            size_kb = p.stat().st_size / 1024
            size_str = f"{round(size_kb, 1)} KB" if size_kb < 1024 else f"{round(size_kb / 1024, 1)} MB"
            pdf_list.append({
                "filename": p.name,
                "title": p.stem.replace("_", " ").replace("-", " ").title(),
                "size": size_str,
                "url": url_for("static", filename=f"courses/{category_name}/{p.name}"),
            })
        pdf_list.sort(key=lambda x: x["title"])
        return pdf_list

    software_pdfs = scan_pdfs(software_dir, "software")
    hardware_pdfs = scan_pdfs(hardware_dir, "hardware")

    return render_template(
        "courses.html",
        profile=profile,
        software_pdfs=software_pdfs,
        hardware_pdfs=hardware_pdfs,
    )


@app.route("/internships")
@login_required
def internships():
    profile = get_profile(session["uid"]) or {}
    skills = str(profile.get("skills") or profile.get("primary_skills") or "").strip()

    ranked_matches = []
    if skills:
        all_opportunities = get_all_internships(profile)
        ranked_matches = get_gemini_recommendations(profile, all_opportunities)

    return render_template(
        "internships.html",
        profile=profile,
        matches=ranked_matches,
        gemini_active=bool(get_gemini_api_key())
    )


@app.route("/placements")
@login_required
def placements():
    profile = get_profile(session["uid"]) or {}
    placements_list = get_placements()
    return render_template("placements.html", profile=profile, placements=placements_list)


@app.route("/api/profile", methods=["POST"])
@login_required
def save_profile():
    """API endpoint to update profile asynchronously."""
    data = request.form if request.form else request.json
    upsert_profile(
        session["uid"],
        email=session.get("email", ""),
        name=data.get("name", ""),
        degree=data.get("degree", ""),
        skills=data.get("skills", ""),
        location=data.get("location", "Any"),
    )
    return jsonify({"status": "saved"})


@app.route("/recommend", methods=["POST"])
@login_required
def recommend():
    return redirect(url_for("internships"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
