import urllib.request
import json
import time
from pathlib import Path
import re

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_EXPIRATION_SECONDS = 1800  # 30 minutes


def clean_html(raw_html):
    if not raw_html:
        return ""
    cleanr = re.compile(r"<.*?>")
    cleantext = re.sub(cleanr, " ", raw_html)
    return " ".join(cleantext.split())


def get_cache_key(profile):
    """Generates a stable cache key based on user profile search criteria."""
    skills = str(profile.get("skills") or "").lower().strip()
    sectors = str(profile.get("preferred_sectors") or "").lower().strip()
    degree = str(profile.get("degree") or "").lower().strip()
    clean_str = f"{skills}_{sectors}_{degree}"
    return re.sub(r"[^a-zA-Z0-9_]", "_", clean_str)[:60]


def load_cached_user_internships(cache_key):
    cache_file = CACHE_DIR / f"internships_{cache_key}.json"
    if not cache_file.exists():
        return None
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if time.time() - data.get("timestamp", 0) < CACHE_EXPIRATION_SECONDS:
                return data.get("internships", [])
    except Exception as e:
        print("Cache read notice:", e)
    return None


def save_cached_user_internships(cache_key, internships):
    cache_file = CACHE_DIR / f"internships_{cache_key}.json"
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": time.time(),
                "internships": internships
            }, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print("Cache save notice:", e)


def fetch_internet_internships(profile):
    """Fetches real-time open internship opportunities from public API feeds filtered by user data."""
    live_items = []
    
    user_skills_raw = str(profile.get("skills") or profile.get("primary_skills") or "").lower()
    user_skills = [s.strip() for s in user_skills_raw.split(",") if s.strip()]
    user_sectors = [s.strip().lower() for s in str(profile.get("preferred_sectors") or "").split(",") if s.strip()]
    user_field = str(profile.get("field_of_study") or "").lower()

    # 1. Fetch from Arbeitnow Public API
    try:
        url = "https://www.arbeitnow.com/api/job-board-api"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "SkillBridge-AI-Agent/2.0 (National Skill Bridge)"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for job in data.get("data", []):
                tags = [t.strip().lower() for t in job.get("tags", []) if t.strip()]
                is_remote = bool(job.get("remote"))
                location = "Remote" if is_remote else (job.get("location") or "Any")
                desc_text = clean_html(job.get("description", ""))[:280]

                # Determine sector
                tags_str = " ".join(tags) + " " + job.get("title", "").lower()
                sector = "IT & Software"
                if any(w in tags_str for w in ["finance", "accounting", "banking", "tax"]):
                    sector = "Banking & Finance"
                elif any(w in tags_str for w in ["marketing", "sales", "seo", "content", "growth"]):
                    sector = "Marketing & Sales"
                elif any(w in tags_str for w in ["manufacturing", "mechanical", "electrical", "hardware", "civil"]):
                    sector = "Manufacturing & Engineering"
                elif any(w in tags_str for w in ["data", "ai", "machine learning", "python", "analytics", "sql"]):
                    sector = "Data Science & AI"

                # Filter relevance to user skills or sectors
                is_relevant = False
                if not user_skills:
                    is_relevant = True
                else:
                    for us in user_skills:
                        if us in tags_str or any(us in t for t in tags):
                            is_relevant = True
                            break
                    if not is_relevant and user_sectors:
                        if any(sec in sector.lower() for sec in user_sectors):
                            is_relevant = True
                    if not is_relevant and user_field and user_field in tags_str:
                        is_relevant = True

                if is_relevant:
                    live_items.append({
                        "company_name": job.get("company_name", "Global Enterprise"),
                        "job_title": job.get("title", "Associate Intern"),
                        "sector": sector,
                        "location": location,
                        "pay": "₹25,000 - ₹50,000 / month (or Equivalent)",
                        "job_type": "Internship / Full-time",
                        "qualifications_required": ["B.Tech", "B.Sc", "BCA", "B.Com", "Any"],
                        "skills_and_competencies": tags if tags else ["problem solving", "communication", "technology"],
                        "work_location_type": "Remote" if is_remote else "In person",
                        "description": desc_text + ("..." if len(desc_text) >= 280 else ""),
                        "apply_url": job.get("url", "https://www.arbeitnow.com"),
                        "source": "Live Web Feed",
                        "source_badge": "🌐 Live Web Opportunity"
                    })
    except Exception as e:
        print("Arbeitnow live fetch notice:", e)

    # 2. Fetch from Remotive Public API
    try:
        url = "https://remotive.com/api/remote-jobs?limit=30"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "SkillBridge-AI-Agent/2.0"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for job in data.get("jobs", []):
                tags = [t.strip().lower() for t in job.get("tags", []) if t.strip()]
                desc_text = clean_html(job.get("description", ""))[:280]
                category = job.get("category", "Software Development")
                tags_str = " ".join(tags) + " " + job.get("title", "").lower()

                # Filter relevance
                is_relevant = False
                if not user_skills:
                    is_relevant = True
                else:
                    for us in user_skills:
                        if us in tags_str:
                            is_relevant = True
                            break

                if is_relevant:
                    live_items.append({
                        "company_name": job.get("company_name", "Tech Partner"),
                        "job_title": job.get("title", "Remote Trainee Intern"),
                        "sector": "IT & Software" if "software" in category.lower() else "Enterprise Partner",
                        "location": "Remote / Flexible",
                        "pay": "Competitive Industry Stipend",
                        "job_type": "Internship",
                        "qualifications_required": ["B.Tech", "B.Sc", "BCA", "Any"],
                        "skills_and_competencies": tags[:6] if tags else ["python", "data analysis", "problem solving"],
                        "work_location_type": "Remote",
                        "description": desc_text + ("..." if len(desc_text) >= 280 else ""),
                        "apply_url": job.get("url", "https://remotive.com"),
                        "source": "Live Web Feed",
                        "source_badge": "🌐 Remote Global Opportunity"
                    })
    except Exception as e:
        print("Remotive live fetch notice:", e)

    return live_items


def load_pmis_national_partners(profile):
    """Loads and pre-filters curated PMIS enterprise partners based on candidate profile."""
    companies_path = Path(__file__).parent / "companies.json"
    if not companies_path.exists():
        return []
    try:
        with open(companies_path, "r", encoding="utf-8") as f:
            raw_companies = json.load(f)
            
            user_degree = str(profile.get("degree") or "").lower().strip()
            user_skills = [s.strip().lower() for s in str(profile.get("skills") or "").split(",") if s.strip()]
            user_sectors = [s.strip().lower() for s in str(profile.get("preferred_sectors") or "").split(",") if s.strip()]

            items = []
            for c in raw_companies:
                comp_skills = [s.lower() for s in c.get("skills", [])]
                comp_degrees = [d.lower() for d in c.get("degrees", ["any"])]
                comp_sector = c.get("sector", "Enterprise").lower()

                # Calculate general alignment
                degree_eligible = ("any" in comp_degrees) or (user_degree in comp_degrees) or (not user_degree)
                skill_aligned = any(us in comp_skills or any(us in cs for cs in comp_skills) for us in user_skills) if user_skills else True
                sector_aligned = any(sec in comp_sector for sec in user_sectors) if user_sectors else True

                # Include all partners or prioritize aligned
                items.append({
                    "company_name": c.get("name", "PMIS Partner"),
                    "job_title": f"{c.get('sector', 'Enterprise')} Trainee Intern",
                    "sector": c.get("sector", "Enterprise"),
                    "location": c.get("location", "Any"),
                    "pay": "₹15,000 - ₹35,000 / month (PMIS Govt Stipend)",
                    "job_type": "Govt PM Scheme Internship",
                    "qualifications_required": c.get("degrees", ["Any"]),
                    "skills_and_competencies": c.get("skills", []),
                    "work_location_type": "In person" if c.get("location") != "Remote" else "Remote",
                    "description": f"Official internship opportunity under Prime Minister's Internship Scheme with {c.get('name')} in {c.get('sector')}.",
                    "apply_url": "https://pminternship.mca.gov.in/",
                    "source": "PMIS Partner",
                    "source_badge": "🏛️ PMIS Partner",
                    "degree_eligible": degree_eligible,
                    "skill_aligned": skill_aligned,
                    "sector_aligned": sector_aligned
                })
            return items
    except Exception as e:
        print("Error loading companies.json:", e)
        return []


def get_all_internships(profile=None):
    """Combines user-targeted internet live feeds with PMIS partner dataset."""
    if not profile:
        profile = {}

    cache_key = get_cache_key(profile)
    cached = load_cached_user_internships(cache_key)
    if cached:
        return cached

    pmis_opps = load_pmis_national_partners(profile)
    live_opps = fetch_internet_internships(profile)

    all_items = pmis_opps + live_opps
    if all_items:
        save_cached_user_internships(cache_key, all_items)

    return all_items
