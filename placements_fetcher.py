import json
import time
import urllib.request
from pathlib import Path

CACHE_FILE = Path(__file__).parent / "cached_placements.json"
LOCAL_FALLBACK_FILE = Path(__file__).parent / "placements.json"
CACHE_EXPIRY_SECONDS = 3600  # 1 hour cache


def fetch_from_arbeitnow_api():
    """Fetches real live job postings from Arbeitnow public API."""
    url = "https://www.arbeitnow.com/api/job-board-api"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "SkillBridge-PlacementPortal/1.0", "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
        raw_jobs = payload.get("data", [])

    parsed_jobs = []
    for idx, j in enumerate(raw_jobs[:25]):  # Process top 25 fresh postings
        title = j.get("title", "Career Opportunity").strip()
        company = j.get("company_name", "Enterprise Partner").strip()
        location = j.get("location", "Remote / Flexible").strip() or "Flexible Location"
        is_remote = j.get("remote", False)
        tags = j.get("tags", [])
        job_types = j.get("job_types", ["Full-time"])
        url_link = j.get("url", "#")
        desc = j.get("description", "Detailed description available on partner portal.")
        created_at = j.get("created_at")

        # Determine work location type
        if is_remote:
            work_type = "Remote"
        elif "hybrid" in location.lower() or "hybrid" in str(tags).lower():
            work_type = "Hybrid"
        else:
            work_type = "In person"

        # Determine sector from tags/title
        sector = "Technology & IT"
        lower_tags = [t.lower() for t in tags]
        lower_title = title.lower()
        if any(t in lower_tags for t in ["marketing", "sales", "growth"]) or "marketing" in lower_title:
            sector = "Marketing & Growth"
        elif any(t in lower_tags for t in ["finance", "accounting", "banking"]) or "finance" in lower_title:
            sector = "Banking & Finance"
        elif any(t in lower_tags for t in ["hardware", "embedded", "mechanical", "electrical"]):
            sector = "Core Engineering"
        elif any(t in lower_tags for t in ["data", "analytics", "ai", "machine-learning", "python"]):
            sector = "Data Science & AI"

        parsed_jobs.append({
            "id": f"live-job-{idx+1}",
            "company_name": company,
            "job_title": title,
            "sector": sector,
            "location": location,
            "pay": "Competitive / Industry Standard",
            "job_type": ", ".join(job_types) if job_types else "Full-time",
            "qualifications_required": [
                "B.Tech / B.E.",
                "B.Sc / BCA",
                "Graduate Degree / Diploma"
            ],
            "skills_and_competencies": tags if tags else ["problem solving", "communication", "teamwork"],
            "work_location_type": work_type,
            "description": desc,
            "url": url_link,
            "posted_date": time.strftime("%d %b %Y", time.gmtime(created_at)) if created_at else "Recently",
            "source": "Live Aggregator Feed"
        })
    return parsed_jobs


def get_placements(force_refresh=False):
    """Returns real placement listings, with caching and fallback."""
    now = time.time()

    # Check cache
    if not force_refresh and CACHE_FILE.exists():
        try:
            mtime = CACHE_FILE.stat().st_mtime
            if now - mtime < CACHE_EXPIRY_SECONDS:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                    if cached_data and len(cached_data) > 0:
                        return cached_data
        except Exception:
            pass

    # Try fetching fresh live listings
    try:
        live_jobs = fetch_from_arbeitnow_api()
        if live_jobs:
            # Also append local Indian enterprise placements
            if LOCAL_FALLBACK_FILE.exists():
                with open(LOCAL_FALLBACK_FILE, "r", encoding="utf-8") as f:
                    local_data = json.load(f)
                    for item in local_data:
                        item["source"] = "PMIS Partner Enterprise"
                        if "url" not in item:
                            item["url"] = "https://pminternship.mca.gov.in"
                    live_jobs = local_data + live_jobs

            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(live_jobs, f, indent=2)
            return live_jobs
    except Exception as e:
        print(f"[Warning] Failed to fetch live job aggregator data: {e}")

    # Fallback to local placements.json if API fails
    if LOCAL_FALLBACK_FILE.exists():
        with open(LOCAL_FALLBACK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    return []
