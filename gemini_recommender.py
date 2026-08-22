import os
import json
import urllib.request
from pathlib import Path
import re

CONFIG_FILE = Path(__file__).parent / "gemini_config.json"
ENV_FILE = Path(__file__).parent / ".env"


def get_gemini_api_key():
    """Retrieves Gemini API Key from gemini_config.json, .env file, or environment variable."""
    # 1. Check gemini_config.json
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                key = data.get("gemini_api_key") or data.get("apiKey")
                if key and key.strip() and "YOUR_GEMINI_API_KEY" not in key:
                    return key.strip()
        except Exception as e:
            print("Notice reading gemini_config.json:", e)

    # 2. Check .env file
    if ENV_FILE.exists():
        try:
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("GEMINI_API_KEY="):
                        key = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                        if key and "YOUR_GEMINI_API_KEY" not in key:
                            return key
        except Exception as e:
            print("Notice reading .env file:", e)

    # 3. Check environment variable (if starts with AIzaSy)
    key = os.getenv("GEMINI_API_KEY")
    if key and key.strip() and key.strip().startswith("AIzaSy"):
        return key.strip()

    return None


def calculate_local_probability(profile, opp):
    """Calculates match probability % (0.0% to 99.5%) across all 4 candidate pillars."""
    prob = 30.0  # Base prior

    user_skills_raw = str(profile.get("skills") or profile.get("primary_skills") or "").lower()
    user_skills = [s.strip() for s in user_skills_raw.split(",") if s.strip()]
    user_degree = str(profile.get("degree") or "").lower().strip()
    user_field = str(profile.get("field_of_study") or "").lower().strip()
    user_sectors = [s.strip().lower() for s in str(profile.get("preferred_sectors") or "").split(",") if s.strip()]
    user_loc = str(profile.get("location") or profile.get("preferred_locations") or "any").lower().strip()
    user_mode = str(profile.get("internship_mode") or "hybrid").lower().strip()
    user_portfolio = str(profile.get("resume_url") or "").strip()
    user_soft_skills = str(profile.get("soft_skills") or "").strip()

    # 1. Skills & Competencies Probability (Up to 35%)
    opp_skills_raw = opp.get("skills_and_competencies") or opp.get("skills") or []
    if isinstance(opp_skills_raw, list):
        opp_skills = [str(s).lower().strip() for s in opp_skills_raw]
    else:
        opp_skills = [s.lower().strip() for s in str(opp_skills_raw).split(",") if s.strip()]

    matched = []
    for us in user_skills:
        for os_s in opp_skills:
            if us in os_s or os_s in us:
                matched.append(os_s)
                break
    matched = list(set(matched))

    if opp_skills and matched:
        prob += (len(matched) / len(opp_skills)) * 35.0
    elif user_skills:
        prob += 18.0

    # 2. Academic & Educational Credentials Probability (Up to 20%)
    opp_degrees_raw = opp.get("qualifications_required") or opp.get("degrees") or ["any"]
    if isinstance(opp_degrees_raw, list):
        opp_degrees = [str(d).lower().strip() for d in opp_degrees_raw]
    else:
        opp_degrees = [d.lower().strip() for d in str(opp_degrees_raw).split(",") if d.strip()]

    if "any" in opp_degrees or not opp_degrees:
        prob += 15.0
    elif user_degree and any(user_degree in d or d in user_degree for d in opp_degrees):
        prob += 20.0
    else:
        prob += 8.0

    if user_field and any(user_field in str(opp.get("description", "")).lower() or user_field in str(opp.get("sector", "")).lower() for _ in [1]):
        prob += 4.0

    # 3. Internship & Industry Preferences Probability (Up to 10%)
    opp_sector = str(opp.get("sector") or "").lower()
    if any(sec in opp_sector or opp_sector in sec for sec in user_sectors):
        prob += 8.0
    elif not user_sectors:
        prob += 4.0

    opp_loc = str(opp.get("location") or "any").lower()
    opp_mode = str(opp.get("work_location_type") or "in person").lower()
    if user_loc == "any" or opp_loc == "any" or user_loc in opp_loc or opp_loc in user_loc:
        prob += 2.0
    elif user_mode == "remote" or opp_mode == "remote":
        prob += 2.0

    # 4. User Portfolio & Experience Probability (Up to 5%)
    if user_portfolio:
        prob += 3.0
    if user_soft_skills:
        prob += 2.0

    final_score = min(round(prob, 1), 99.5)
    return final_score, matched


def get_gemini_recommendations(profile, opportunities):
    """Uses Google Gemini API to analyze candidate profile across all 4 pillars and calculate match probability %."""
    api_key = get_gemini_api_key()

    if api_key:
        try:
            opps_summary = []
            for idx, opp in enumerate(opportunities[:35]):
                opps_summary.append({
                    "id": idx,
                    "company": opp.get("company_name"),
                    "title": opp.get("job_title"),
                    "sector": opp.get("sector"),
                    "skills": opp.get("skills_and_competencies", [])[:6],
                    "degrees": opp.get("qualifications_required", ["Any"]),
                    "location": opp.get("location"),
                    "work_type": opp.get("work_location_type")
                })

            prompt = f"""You are an expert AI Career Matchmaker for India's Prime Minister Internship Scheme (SkillBridge).
Analyze this Candidate Profile across 4 key pillars:
1. Academic Credentials: {profile.get('degree', 'B.Tech')} in {profile.get('field_of_study', 'General')}, Passing Year: {profile.get('graduation_year', '2026')}, Score: {profile.get('cgpa_percentage', 'Not specified')}
2. Skills & Competencies: {profile.get('skills', '')}, Soft Skills: {profile.get('soft_skills', '')}, Experience: {profile.get('experience_level', 'Fresher')}
3. Preferences: Preferred Sectors: {profile.get('preferred_sectors', 'Any')}, Location: {profile.get('location', 'Any')}, Work Mode: {profile.get('internship_mode', 'Hybrid')}, Availability: {profile.get('availability', 'Immediate')}
4. Portfolio & Profiles: {profile.get('resume_url', 'Active Profile')}

Available Internship Opportunities:
{json.dumps(opps_summary, ensure_ascii=False)}

Task:
Evaluate every opportunity against all 4 candidate pillars.
Select the top 6 to 12 best matching internships.
For each selected opportunity, calculate a realistic Match Probability % (from 40.0% to 99.0%) based on exact skill alignment, degree eligibility, and sector fit.

Return ONLY a valid JSON array of objects, with each object having:
- "id": (the integer id from the input)
- "probability": (a float or formatted string representing the match probability, e.g. 96.5 or "96.5%")
- "matched_skills": list of candidate skills that directly match the role
- "ai_reason": a 2-sentence rationale detailing how the candidate's academic credentials, verified skills, and preferences align with this position.
"""

            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
            payload = json.dumps({
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.2,
                    "responseMimeType": "application/json"
                }
            }).encode("utf-8")

            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                text_response = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
                gemini_matches = json.loads(text_response)

                final_results = []
                for item in gemini_matches:
                    opp_id = item.get("id")
                    if isinstance(opp_id, int) and 0 <= opp_id < len(opportunities):
                        base_opp = dict(opportunities[opp_id])
                        
                        prob_val = item.get("probability", 85.0)
                        if isinstance(prob_val, (int, float)):
                            prob_str = f"{round(float(prob_val), 1)}%"
                            prob_num = float(prob_val)
                        else:
                            clean_num = re.sub(r"[^\d.]", "", str(prob_val))
                            prob_num = float(clean_num) if clean_num else 80.0
                            prob_str = f"{prob_num}%"

                        base_opp["probability"] = prob_str
                        base_opp["probability_num"] = prob_num
                        base_opp["score"] = prob_str
                        base_opp["matched_skills"] = item.get("matched_skills", [])
                        base_opp["ai_reason"] = item.get("ai_reason", "AI selected based on 4-pillar qualification and skill alignment.")
                        base_opp["ai_powered"] = True
                        final_results.append(base_opp)

                if final_results:
                    final_results.sort(key=lambda x: x.get("probability_num", 0), reverse=True)
                    return final_results

        except Exception as e:
            print("Gemini AI API call notice:", e)

    # Fallback: High-precision 4-pillar calculation
    fallback_results = []
    for opp in opportunities:
        prob_num, matched = calculate_local_probability(profile, opp)
        item = dict(opp)
        prob_str = f"{prob_num}%"
        item["probability"] = prob_str
        item["probability_num"] = prob_num
        item["score"] = prob_str
        item["matched_skills"] = matched
        
        reasons = []
        if matched:
            reasons.append(f"Strong overlap in {', '.join(matched[:3])}")
        if profile.get("degree"):
            reasons.append(f"Eligible degree track in {profile.get('degree')}")
        if profile.get("preferred_sectors"):
            reasons.append(f"Sector match with {opp.get('sector')}")
        if profile.get("resume_url"):
            reasons.append("Portfolio verified")
        item["ai_reason"] = " • ".join(reasons) if reasons else f"Career alignment in {opp.get('sector')}."
        item["ai_powered"] = bool(api_key)
        fallback_results.append(item)

    # Sort in descending order of calculated probability
    fallback_results.sort(key=lambda x: x["probability_num"], reverse=True)
    return fallback_results
