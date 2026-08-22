import math
import re
from collections import Counter
import os
import json

# ---------------------------------------------------------------------------
# High-Precision TF-IDF & Cosine Similarity Vector Space Engine (Zero Cost)
# ---------------------------------------------------------------------------

def tokenize(text):
    """Tokenizes and cleans text into normalized terms."""
    if not text:
        return []
    # Replace non-alphanumeric with spaces, keep lowercase
    words = re.findall(r"\b[a-zA-Z0-9+#.-]+\b", str(text).lower())
    # Stop words to filter out noise
    stopwords = {
        "and", "or", "the", "a", "an", "in", "on", "at", "for", "with", "to", "of",
        "is", "are", "as", "by", "from", "that", "this", "it", "be", "all", "any"
    }
    return [w for w in words if w not in stopwords and len(w) > 1]


def compute_tf(tokens):
    """Computes Term Frequency dictionary."""
    counts = Counter(tokens)
    total = len(tokens) if tokens else 1
    return {word: count / total for word, count in counts.items()}


def compute_cosine_similarity(vec1, vec2):
    """Computes cosine similarity between two term-frequency sparse vectors."""
    intersection = set(vec1.keys()) & set(vec2.keys())
    dot_product = sum(vec1[k] * vec2[k] for k in intersection)
    
    norm1 = math.sqrt(sum(v ** 2 for v in vec1.values()))
    norm2 = math.sqrt(sum(v ** 2 for v in vec2.values()))
    
    if not norm1 or not norm2:
        return 0.0
    return dot_product / (norm1 * norm2)


# ---------------------------------------------------------------------------
# Multi-Factor AI Recommendation Engine
# ---------------------------------------------------------------------------

def build_candidate_corpus(profile):
    """Constructs a rich text profile for semantic vectorization."""
    if not isinstance(profile, dict):
        return ""
    
    parts = []
    parts.append(str(profile.get("skills") or profile.get("primary_skills") or ""))
    parts.append(str(profile.get("field_of_study") or ""))
    parts.append(str(profile.get("degree") or ""))
    parts.append(str(profile.get("soft_skills") or ""))
    parts.append(str(profile.get("preferred_sectors") or ""))
    parts.append(str(profile.get("location") or profile.get("preferred_locations") or ""))
    
    return " ".join(filter(None, parts))


def build_internship_corpus(item):
    """Constructs a rich text opportunity vector for semantic matching."""
    if not isinstance(item, dict):
        return ""
    
    parts = []
    parts.append(str(item.get("job_title") or ""))
    parts.append(str(item.get("company_name") or ""))
    parts.append(str(item.get("sector") or ""))
    skills = item.get("skills_and_competencies") or item.get("skills") or []
    if isinstance(skills, list):
        parts.append(" ".join(skills))
    else:
        parts.append(str(skills))
    degrees = item.get("qualifications_required") or item.get("degrees") or []
    if isinstance(degrees, list):
        parts.append(" ".join(degrees))
    else:
        parts.append(str(degrees))
    parts.append(str(item.get("location") or ""))
    parts.append(str(item.get("description") or ""))
    
    return " ".join(filter(None, parts))


def estimate_selection_probability(opp, fit_score, degree_score):
    """
    Rough estimate of the ODDS OF ACTUALLY BEING SELECTED for this specific
    opportunity -- a different question from "how well does it fit me"
    (that's `fit_score` / final_score).

    This is NOT a statistically validated probability. A real one requires
    historical outcome data (who applied, who got selected) that this
    project doesn't have yet. What this function does instead:

      1. Hard-gates on eligibility: if the candidate doesn't meet the
         degree/qualification bar, no amount of "fit" makes selection likely.
      2. Anchors PMIS listings to a REAL published base rate: government
         data tabled in the Lok Sabha showed ~33% of candidates who applied
         under the PM Internship Scheme received at least one offer across
         both pilot rounds (~60k of ~181k applicants in round 1, a similar
         ratio in round 2 -- MCA reply, reported July 2025).
      3. Uses a labeled PLACEHOLDER base rate for live-feed listings
         (Arbeitnow / Remotive), since no public acceptance-rate data exists
         for open-market internship postings. Replace this constant with a
         real figure as soon as you start logging your own users' outcomes
         (applied -> selected / rejected) -- see note at bottom of file.
      4. Scales that base rate up or down by how strong the match is,
         using the engine's own 35-99.5 score range.

    Always surface this to users as an ESTIMATE ("estimated likelihood"),
    never as a guarantee or a precise statistic.
    """
    # 1. Hard eligibility gate -- an explicit degree/qualification mismatch
    # (the engine's degree_score branch for "does not match") caps this hard,
    # regardless of how well everything else lines up.
    if degree_score <= 5.0:
        return 2.0

    source = str(opp.get("source") or "").lower()
    source_badge = str(opp.get("source_badge") or "").lower()

    if "pmis" in source or "pmis" in source_badge:
        # Real anchor: MCA/Lok Sabha figures, see docstring above.
        base_rate = 33.0
    else:
        # PLACEHOLDER -- no public data backs this number. Swap it out once
        # you have real applied/selected logs from your own users.
        base_rate = 12.0

    # 2. Scale by relative fit within the engine's own score range.
    normalized_fit = (fit_score - 35.0) / (99.5 - 35.0)  # 0.0 (worst) - 1.0 (best)
    multiplier = 0.5 + 1.3 * normalized_fit  # weak fit -> 0.5x, top fit -> ~1.8x

    probability = base_rate * multiplier
    return round(min(max(probability, 2.0), 95.0), 1)


def rank_internships(profile, opportunities):
    """Ranks opportunities with high precision using hybrid semantic cosine similarity and domain filters."""
    if not opportunities:
        return []
    
    candidate_text = build_candidate_corpus(profile)
    candidate_tokens = tokenize(candidate_text)
    candidate_tf = compute_tf(candidate_tokens)

    user_skills_raw = str(profile.get("skills") or profile.get("primary_skills") or "").lower()
    user_skills = [s.strip() for s in user_skills_raw.split(",") if s.strip()]
    user_degree = str(profile.get("degree") or "").strip().lower()
    user_sectors = [s.strip().lower() for s in str(profile.get("preferred_sectors") or "").split(",") if s.strip()]
    user_location = str(profile.get("location") or profile.get("preferred_locations") or "any").strip().lower()
    user_mode = str(profile.get("internship_mode") or "hybrid").strip().lower()

    ranked_results = []

    for opp in opportunities:
        opp_text = build_internship_corpus(opp)
        opp_tokens = tokenize(opp_text)
        opp_tf = compute_tf(opp_tokens)

        # 1. Semantic Vector Cosine Similarity (Up to 40 Points)
        cosine_sim = compute_cosine_similarity(candidate_tf, opp_tf)
        semantic_score = min(cosine_sim * 55.0, 40.0)

        # 2. Hard Skills Overlap (Up to 30 Points)
        opp_skills_raw = opp.get("skills_and_competencies") or opp.get("skills") or []
        if isinstance(opp_skills_raw, str):
            opp_skills = [s.strip().lower() for s in opp_skills_raw.split(",") if s.strip()]
        else:
            opp_skills = [str(s).strip().lower() for s in opp_skills_raw if str(s).strip()]
        
        matched_skills = []
        for us in user_skills:
            for os_skill in opp_skills:
                if us in os_skill or os_skill in us:
                    matched_skills.append(os_skill)
                    break
        matched_skills = list(set(matched_skills))

        skills_score = 0.0
        if opp_skills:
            skills_score = (len(matched_skills) / len(opp_skills)) * 30.0
        elif matched_skills:
            skills_score = 20.0
        else:
            skills_score = 10.0

        # 3. Degree & Academic Eligibility (Up to 15 Points)
        opp_degrees_raw = opp.get("qualifications_required") or opp.get("degrees") or ["any"]
        if isinstance(opp_degrees_raw, str):
            opp_degrees = [d.strip().lower() for d in opp_degrees_raw.split(",") if d.strip()]
        else:
            opp_degrees = [str(d).strip().lower() for d in opp_degrees_raw if str(d).strip()]
        
        degree_score = 0.0
        if not opp_degrees_raw or opp_degrees_raw == ["any"]:
            # Source gave us no degree info at all -> neutral, not a guaranteed match
            degree_score = 10.0
        elif "any" in opp_degrees:
            # Source explicitly said "any degree accepted" -> genuine full match
            degree_score = 15.0
        elif user_degree and any(user_degree in d or d in user_degree for d in opp_degrees):
            degree_score = 15.0
        else:
            degree_score = 5.0

        # 4. Industry Sector Match (Up to 10 Points)
        opp_sector = str(opp.get("sector") or "").lower().strip()
        sector_score = 0.0
        if not opp_sector or not user_sectors:
            # Missing data on either side -> neutral, do NOT auto-award full points.
            # (Guarding here also avoids the classic bug where "" is treated as a
            # substring of everything, which used to make every sector-less job
            # score a "perfect" 10.)
            sector_score = 6.0
        elif any(sec in opp_sector or opp_sector in sec for sec in user_sectors):
            sector_score = 10.0
        else:
            sector_score = 3.0

        # 5. Location & Work Setup (Up to 5 Points)
        opp_loc_raw = str(opp.get("location") or "").lower().strip()
        opp_mode = str(opp.get("work_location_type") or "in person").lower()
        location_score = 0.0
        if not opp_loc_raw or user_location == "any":
            # Unknown on either side -> neutral, not an automatic full match
            location_score = 3.0
        elif user_location in opp_loc_raw or opp_loc_raw in user_location:
            location_score = 5.0
        elif user_mode == "remote" or "remote" in opp_loc_raw or opp_mode == "remote":
            location_score = 4.5
        else:
            location_score = 1.5

        total_score = semantic_score + skills_score + degree_score + sector_score + location_score
        
        # Round and bound score between 30% and 99.5%
        final_score = min(max(round(total_score, 1), 35.0), 99.5)

        # Estimated probability of actually being selected -- a DIFFERENT
        # question from "how well does this fit me". See
        # estimate_selection_probability() for the reasoning and caveats.
        selection_probability = estimate_selection_probability(opp, final_score, degree_score)

        # AI Recommendation Match Explanation
        reason_parts = []
        if matched_skills:
            reason_parts.append(f"Strong competency in {', '.join(matched_skills[:3])}")
        if degree_score >= 15:
            reason_parts.append(f"Eligible for {opp.get('qualifications_required', ['All Degrees'])[0] if isinstance(opp.get('qualifications_required'), list) and opp.get('qualifications_required') else 'Degree Track'}")
        if sector_score >= 10:
            reason_parts.append(f"Direct alignment with target sector ({opp.get('sector')})")
        if not reason_parts:
            reason_parts.append("Broad cross-domain career alignment")

        ai_reason = " • ".join(reason_parts)

        ranked_results.append({
            "company_name": opp.get("company_name", "Enterprise Partner"),
            "job_title": opp.get("job_title", "Associate Trainee"),
            "sector": opp.get("sector", "Enterprise"),
            "location": opp.get("location", "Any"),
            "pay": opp.get("pay", "Standard PMIS Stipend"),
            "job_type": opp.get("job_type", "Internship"),
            "work_location_type": opp.get("work_location_type", "In person"),
            "qualifications_required": opp.get("qualifications_required", ["Any"]),
            "skills_and_competencies": opp_skills,
            "matched_skills": matched_skills,
            "description": opp.get("description", ""),
            "apply_url": opp.get("apply_url", "#"),
            "source": opp.get("source", "PMIS Partner"),
            "source_badge": opp.get("source_badge", "🏛️ PMIS Partner"),
            "score": final_score,
            "ai_reason": ai_reason,
            "selection_probability": selection_probability,
        })

    # Sort in descending order of accuracy rank
    ranked_results.sort(key=lambda x: x["score"], reverse=True)
    return ranked_results


def calculate_match_score(profile, company):
    """Convenience function to calculate score for a single opportunity."""
    results = rank_internships(profile, [company])
    return results[0]["score"] if results else 50.0


# ---------------------------------------------------------------------------
# Pluggable AI LLM Adapter Hook (For Google Gemini / Groq / HuggingFace)
# ---------------------------------------------------------------------------
class LLMRecommender:
    """Optional extension to connect free AI cloud APIs (Google Gemini, Groq, Cohere)
    when API keys are provided by user."""

    @staticmethod
    def is_ai_available():
        return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GROQ_API_KEY") or os.getenv("HUGGINGFACE_API_KEY"))

    @staticmethod
    def explain_with_ai(candidate_profile, top_match):
        """Generates natural language candidate-job fit rationale via Free AI API if configured."""
        gemini_key = os.getenv("GEMINI_API_KEY")
        if gemini_key:
            try:
                import urllib.request
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
                prompt = (
                    f"Candidate Profile: {candidate_profile.get('name')}, degree {candidate_profile.get('degree')}, skills: {candidate_profile.get('skills')}. "
                    f"Job Opportunity: {top_match.get('job_title')} at {top_match.get('company_name')}. "
                    f"In 2 sentences, explain why this internship is a high fit."
                )
                payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
                req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    res_json = json.loads(resp.read().decode("utf-8"))
                    return res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
            except Exception as e:
                print("Gemini API call notice:", e)

        return top_match.get("ai_reason", "High vector alignment between candidate skills and company job profile.")
