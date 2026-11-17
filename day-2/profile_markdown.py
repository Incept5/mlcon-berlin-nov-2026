"""LinkedIn profile: raw browser data -> Proxycurl-format JSON -> laid-out Markdown.

The JSON uses Proxycurl's profile schema (public_identifier, full_name, experiences[{starts_at:{day,month,year},
company, title, ...}], education, certifications, skills, recommendations, ...), the format of the 2024 archive in
PycharmProjects/pythonProject/linkedin. What Proxycurl had no field for goes in "extra": endorsement counts, who wrote
each recommendation and when, employment types, post reactions, the local photo.

    python profile_markdown.py output/jentaylor2.json           # re-render output/jentaylor2.md from the JSON
    python profile_markdown.py old/*.json --out /tmp/md          # works on Proxycurl files too

No model involved: plain rules over the entries the browser found. The page structure is LinkedIn's (Nov 2026)
and will drift; text the rules don't recognise is kept in descriptions rather than dropped.
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

DATE = re.compile(r"((19|20)\d{2}.*[–-].*((19|20)\d{2}|Present))|^Issued |"
                  r"^(January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4}|"
                  r"^(19|20)\d{2}$")
DURATION = re.compile(r"^(Present|\d+ (yrs?|mos?)( \d+ mos?)?)$")
SKILLS_LINE = re.compile(r"(and \+\d+ skills?$|^Skills: )")
SKILL_NOISE = re.compile(r"^(All|Industry Knowledge|Tools & Technologies|Interpersonal Skills|Other Skills|Skills)$|"
                         r"^Endorsed by |^\d+ experiences? | at |^Passed LinkedIn Skill Assessment")
ENDORSE = re.compile(r"^(\d+) endorsements?$")
POST_TYPES = ("Post", "Article", "Document", "Video", "Image")
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
COUNTRIES = {"United Kingdom": "UK", "United States of America": "US", "Germany": "DE", "France": "FR", "United States": "US", "Netherlands": "NL",
             "Ireland": "IE", "Spain": "ES", "Italy": "IT", "Switzerland": "CH", "Austria": "AT", "Belgium": "BE",
             "Sweden": "SE", "Denmark": "DK", "Norway": "NO", "Finland": "FI", "Poland": "PL", "Portugal": "PT",
             "India": "IN", "Canada": "CA", "Australia": "AU", "Singapore": "SG", "Japan": "JP"}


def ymd(text):
    """'May 2023' / 'Sep 2019' / '2014' / 'November 13, 2026' -> Proxycurl {day, month, year}; 'Present' -> None."""
    if not text or "Present" in text:
        return None
    m = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December) (\d{1,2}), (\d{4})", text)
    if m:
        return {"day": int(m.group(2)), "month": MONTHS.index(m.group(1)[:3]) + 1, "year": int(m.group(3))}
    m = re.search(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w* (\d{1,2}), ((?:19|20)\d{2})\b", text)
    if m:
        return {"day": int(m.group(2)), "month": MONTHS.index(m.group(1)) + 1, "year": int(m.group(3))}
    m = re.search(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w* ((?:19|20)\d{2})\b", text)
    if m:
        return {"day": 1, "month": MONTHS.index(m.group(1)) + 1, "year": int(m.group(2))}
    m = re.search(r"\b((?:19|20)\d{2})\b", text)
    return {"day": 1, "month": 1, "year": int(m.group(1))} if m else None


def span(text):
    """'May 2023 – Present · 3 yrs 7 mos' -> (starts_at, ends_at)."""
    text = text.split(" · ")[0].replace(" - ", " – ")
    a, _, b = text.partition(" – ")
    return ymd(a), (ymd(b) if b else ymd(a))


# ---- raw page data -> Proxycurl JSON -----------------------------------------------------------------------------
def _sections(raw):
    """Section title -> section; where a title repeats, keep the smaller one (the section, not its container)."""
    out = {}
    for s in raw["sections"]:
        t = re.sub(r"\s*\(\d+\)$", "", s["title"])
        if t and (t not in out or len(s["lines"]) < len(out[t]["lines"])):
            out[t] = s
    return out


def _strip(entry, title):
    return entry[1:] if entry and entry[0] == title else entry


def _date_index(e):
    return next((i for i, l in enumerate(e) if DATE.search(l)), None)


def _experiences(entries):
    jobs = []
    for e in entries:
        e = _strip(e, "Experience")
        d = _date_index(e)
        if d is None:
            jobs.append({"title": e[0] if e else "", "description": "\n".join(e[1:])})
            continue
        company, _, kind = (e[1] if d >= 2 else "").partition(" · ")
        start, end = span(e[d])
        rest = e[d + 1:]
        while rest and DURATION.match(rest[0]):
            rest = rest[1:]
        place = ""
        if rest and len(rest[0]) <= 60 and not re.search(r"[.?!:]$", rest[0]):
            place, rest = rest[0], rest[1:]
        skills, more = [], 0
        for line in [l for l in rest if SKILLS_LINE.search(l)][:1]:
            m = re.search(r"and \+(\d+) skills?$", line)
            more = int(m.group(1)) if m else 0
            names = re.sub(r" and \+\d+ skills?$", "", re.sub(r"^Skills: ", "", line))
            skills = [s.strip() for s in re.split(r",\s*| and ", names) if s.strip()]
        jobs.append({"starts_at": start, "ends_at": end if "Present" not in e[d] else None, "company": company,
                     "company_linkedin_profile_url": None, "title": e[0],
                     "description": "\n".join(l for l in rest if not SKILLS_LINE.search(l)),
                     "location": place, "logo_url": None,
                     # not in Proxycurl's schema:
                     "employment_type": kind, "skills": skills, "more_skills": more})
    return jobs


def _education(entries):
    out = []
    for e in entries:
        e = _strip(e, "Education")
        if not e:
            continue
        when = next((l for l in e[1:] if DATE.search(l)), "")
        other = [l for l in e[1:] if not DATE.search(l)]
        degree, _, field = (other[0] if other else "").partition(", ")
        start, end = span(when) if when else (None, None)
        out.append({"starts_at": start, "ends_at": end, "field_of_study": field or None, "degree_name": degree or None,
                    "school": e[0], "school_linkedin_profile_url": None, "description": "\n".join(other[1:]) or None,
                    "logo_url": None, "grade": None, "activities_and_societies": None})
    return out


def _certifications(entries):
    out = []
    for e in (_strip(x, "Licenses & certifications") for x in entries):
        if not e:
            continue
        issued = next((l for l in e[1:] if l.startswith("Issued")), "")
        cred = next((l for l in e[1:] if l.startswith("Credential ID")), "")
        authority = next((l for l in e[1:] if l not in (issued, cred)), None)
        out.append({"starts_at": ymd(issued), "ends_at": None, "name": e[0],
                    "license_number": cred.replace("Credential ID", "").strip() or None,
                    "display_source": None, "authority": authority, "url": None})
    return out


def _awards(entries):
    out = []
    for e in (_strip(x, "Honors & awards") for x in entries):
        if not e:
            continue
        issuer_line = next((l for l in e[1:] if l.startswith("Issued by")), "")
        issuer = re.sub(r"^Issued by ", "", issuer_line.split(" · ")[0]) or None
        out.append({"title": e[0], "issuer": issuer, "issued_on": ymd(issuer_line),
                    "description": "\n".join(l for l in e[1:] if l != issuer_line) or None})
    return out


def _skills(lines):
    skills = []
    for l in lines:
        m = ENDORSE.match(l)
        if m and skills:
            skills[-1][1] = int(m.group(1))
        elif not SKILL_NOISE.search(l) and len(l) < 60 and not any(s[0] == l for s in skills):
            skills.append([l, 0])
    return sorted(skills, key=lambda s: -s[1])


def _recommendations(entries):
    out = []
    for e in entries:
        d = _date_index(e)
        if not d:
            continue
        m = re.match(r"^(\w+ \d{1,2}, \d{4}),? ?(.*)$", e[d])
        out.append({"name": e[0], "headline": next((l for l in e[1:d] if not l.startswith("·")), ""),
                    "date": m.group(1) if m else e[d], "relationship": m.group(2) if m else "",
                    "text": "\n\n".join(re.sub(r"\s{2,}", " ", l) for l in e[d + 1:])})
    return out


def _posts(items):
    out = []
    for p in items:
        kind = next((l for l in p[:2] if l in POST_TYPES), "Post")
        p = [l for l in p if l not in POST_TYPES]
        when = next((l for l in p[:5] if re.match(r"^\d+(h|d|w|mo|yr)\b", l)), "")
        if when:
            p = p[p.index(when) + 1:]
        stats = next((l for l in p if re.match(r"^[\d,]+ (reactions?|comments?|reposts?)\b", l)), "")
        text = [l for l in p if l != stats and not re.match(r"^[\d,]+ ·", l)]
        if text:
            out.append({"type": kind, "text": "\n".join(text), "when": when.replace(" • ", " · "), "stats": stats})
    return out


def _interests(lines):
    out = []
    for i, l in enumerate(lines):
        m = re.match(r"^(.*), (Company|Group|School|Newsletter|Person)$", l)
        if m:
            f = next((x for x in lines[i + 1:i + 4] if re.search(r"(followers|members)$", x)), "")
            out.append({"name": m.group(1), "type": m.group(2).lower(), "followers": f})
    return out


def _volunteer(entries):
    out = []
    for e in (_strip(x, "Volunteering") for x in entries):
        d = _date_index(e)
        if not e or d is None:
            continue
        start, end = span(e[d])
        rest = e[d + 1:]
        cause = rest[0] if rest and len(rest[0]) <= 40 and not rest[0].startswith("http") else None
        rest = rest[1:] if cause else rest
        out.append({"starts_at": start, "ends_at": None if "Present" in e[d] else end, "title": e[0],
                    "cause": cause, "company": e[1] if d >= 2 else None, "company_linkedin_profile_url": None,
                    "description": "\n".join(l for l in rest if not l.startswith("http")) or None, "logo_url": None,
                    "url": next((l for l in rest if l.startswith("http")), None)})
    return out


def _publications(lines):
    out, i = [], 0
    while i < len(lines) - 1:
        m = re.match(r"^(.*?) · (\w{3} \d{1,2}, \d{4}|\w{3} \d{4}|\d{4})$", lines[i + 1])
        if m:
            pub = {"name": lines[i], "publisher": m.group(1), "published_on": ymd(m.group(2)), "description": [], "url": None}
            i += 2
            while i < len(lines) and not (i + 1 < len(lines) and re.match(r"^.*? · (\w{3} \d{1,2}, \d{4}|\w{3} \d{4}|\d{4})$", lines[i + 1])):
                if lines[i] != "Show publication":
                    pub["description"].append(lines[i])
                i += 1
            pub["description"] = "\n".join(pub["description"]) or None
            out.append(pub)
        else:
            i += 1
    return out


def _organisations(entries):
    out = []
    for e in entries:
        if len(e) < 2:
            continue
        role, _, dates = e[1].partition(" · ")
        start, end = span(dates) if dates else (None, None)
        out.append({"starts_at": start, "ends_at": None if "Present" in dates else end, "org_name": e[0],
                    "title": role or None, "description": "\n".join(l for l in e[2:] if not l.startswith("http")) or None})
    return out


def _languages(lines):
    return [l for l in lines if not re.search(r"proficiency$", l, re.I)]


CONTACT_LABELS = {"Website", "Websites", "Phone", "Email", "IM", "Address", "Birthday", "Connected since", "Twitter"}


def _contact(lines):
    """The Contact info pop-up: label lines ("Email", "Phone", …) each followed by their values."""
    out, label = {}, None
    for l in lines or []:
        if l in ("Contact info",) or re.search(r"notifications?$", l):
            continue
        if l in CONTACT_LABELS or l.endswith("’s profile") or l.endswith("'s profile"):
            label = "Profile" if "profile" in l else l
            continue
        if label:
            out.setdefault(label, []).append(l)
    return out


def _groups(lines):
    """Interests → Groups tab: a group's name, then "N members" (or followers)."""
    return [lines[i] for i in range(len(lines) - 1)
            if re.search(r"^[\d,.]+[KM]? (members|followers)$", lines[i + 1]) and not re.search(r"(members|followers)$", lines[i])]


def _number(text):
    m = re.search(r"([\d,]+)", text or "")
    return int(m.group(1).replace(",", "")) if m else None


def to_proxycurl(raw):
    S = _sections(raw)
    name = raw["name"]
    head = S.get(name, {"lines": [name]})["lines"]
    degree = next((l.strip("·• ") for l in head[1:3] if l.startswith(("·", "•"))), "")
    info = [l for l in head[1:] if not l.startswith(("·", "•"))]
    headline = info[0] if info else ""
    location = next((l for l in info[1:] if not re.search(r"followers|connections|\+ \d+ more|^My website$|^Contact info$", l)), "")
    parts = [x.strip() for x in location.split(",")] if location else []
    country = parts[-1] if parts else None
    about = S.get("About", {}).get("lines", [])[1:]
    top = []
    if "Top skills" in about:
        k = about.index("Top skills")
        top = [t.strip() for t in " ".join(about[k + 1:k + 2]).split("•") if t.strip()]
        about = about[:k]
    detail = raw.get("details", {})
    skill_lines = next((s["lines"] for s in detail.get("skills", []) if s["lines"][:1] == ["Skills"]),
                       S.get("Skills", {}).get("lines", [])[1:])
    skills = _skills(skill_lines)
    recs = _recommendations(next((s["entries"] for s in detail.get("recommendations", []) if s["entries"]),
                                 S.get("Recommendations", {}).get("entries", [])))
    received = next((int(m.group(1)) for l in S.get("Recommendations", {}).get("lines", [])
                     for m in [re.match(r"^Received \((\d+)\)$", l)] if m), None)
    def full(key, title):
        """Entries from the "Show all" page when there is one, else from the profile page."""
        big = max(detail.get(key, []), key=lambda s: len(s["entries"]), default=None)
        return big["entries"] if big and big["entries"] else S.get(title, {}).get("entries", [])

    def full_lines(key, title):
        big = max(detail.get(key, []), key=lambda s: len(s["lines"]), default=None)
        return big["lines"] if big and big["lines"] and big["lines"][0] == title else S.get(title, {}).get("lines", [])

    jobs = _experiences(full("experience", "Experience"))
    tabs = raw.get("interests") or {}
    interests = _interests(tabs.get("Companies") or S.get("Interests", {}).get("lines", []))
    groups = _groups(tabs.get("Groups") or [])
    contact = _contact(raw.get("contact"))
    first, _, last = name.partition(" ")
    current = next((j for j in jobs if j.get("starts_at") and j.get("ends_at") is None), None)
    connections = next((_number(l) for l in info if l.endswith("connections") and "mutual" not in l), None)
    return {
        "public_identifier": raw["slug"],
        "profile_pic_url": raw.get("photoUrl"),
        "background_cover_image_url": raw.get("coverUrl"),
        "first_name": first, "last_name": last, "full_name": name,
        "follower_count": next((_number(l) for l in info + S.get("Activity", {}).get("lines", [])[1:3] if l.endswith("followers")), None),
        "occupation": f"{current['title']} at {current['company']}" if current and current["company"] else None,
        "headline": headline,
        "summary": "\n".join(about) or None,
        "country": COUNTRIES.get(country), "country_full_name": country,
        "city": parts[0] if len(parts) > 1 else None, "state": parts[1] if len(parts) > 2 else None,
        "experiences": jobs,
        "education": _education(S.get("Education", {}).get("entries", [])),
        "languages": _languages(full_lines("languages", "Languages")[1:]),
        "accomplishment_organisations": _organisations(full("organizations", "Organizations")),
        "accomplishment_publications": _publications(full_lines("publications", "Publications")[1:]),
        "accomplishment_honors_awards": _awards(full("honors", "Honors & awards")),
        "accomplishment_patents": [],
        "accomplishment_courses": [{"name": l, "number": None} for l in S.get("Courses", {}).get("lines", [])[1:]],
        "accomplishment_projects": [], "accomplishment_test_scores": [],
        "volunteer_work": _volunteer(full("volunteering-experiences", "Volunteering")),
        "certifications": _certifications(full("certifications", "Licenses & certifications")),
        "connections": connections,
        "people_also_viewed": [],                  # deliberately not collected: other people's profiles
        "recommendations": [f"{r['name']}\n\n\n\n{r['text']}" for r in recs],
        "activities": [{"title": p["text"].split("\n")[0], "link": None, "activity_status": f"Posted by {name}"}
                       for p in _posts(S.get("Activity", {}).get("posts", []))],
        "similarly_named_profiles": [], "articles": [],
        "groups": [{"profile_pic_url": None, "name": g, "url": None} for g in groups],
        "skills": [s[0] for s in skills],
        "inferred_salary": None, "gender": None, "birth_date": None, "industry": None,
        "personal_emails": contact.get("Email", []), "personal_numbers": contact.get("Phone", []),   # Contact info pop-up
        "interests": [i["name"] for i in interests],
        "extra": {                                 # what Proxycurl had no field for
            "source": "browser_tool_call.py (Ego Lite)", "retrieved": date.today().isoformat(),
            "profile_pic_file": raw.get("photo"), "connection_degree": degree,
            "contact": {k: v for k, v in contact.items() if k not in ("Email", "Phone")},
            "connections_text": next((l for l in info if l.endswith("connections") and "mutual" not in l), None),
            "current_company": next((l for l in info if re.search(r"\+ \d+ more", l)), None),
            "top_skills": top, "services": S.get("Services", {}).get("lines", [])[1:],
            "skill_endorsements": {s[0]: s[1] for s in skills if s[1]},
            "recommendations_received": received, "recommendations_detail": recs,
            "featured": _posts(S.get("Featured", {}).get("posts", [])),
            "activity_posts": _posts(S.get("Activity", {}).get("posts", [])),
            "interests_detail": interests,
            "causes": [c.strip() for c in " • ".join(S.get("Causes", {}).get("lines", [])[1:]).split("•") if c.strip()],
        },
    }


# ---- Proxycurl JSON -> Markdown ----------------------------------------------------------------------------------
def when(d):
    if not d:
        return "Present"
    return str(d["year"]) if d.get("month") in (None, 1) and d.get("day") in (None, 1) else f"{MONTHS[d['month'] - 1]} {d['year']}"


def length(a, b):
    if not a:
        return ""
    b = b or {"year": date.today().year, "month": date.today().month}
    months = (b["year"] - a["year"]) * 12 + (b.get("month") or 1) - (a.get("month") or 1) + 1
    y, m = divmod(max(months, 1), 12)
    return " ".join(x for x in (f"{y} yr{'s' * (y > 1)}" if y else "", f"{m} mo{'s' * (m > 1)}" if m else "") if x)


def body(text):
    """Paragraphs, with bullet lists for "•" lines, numbered lines, and runs of short headline-like lines."""
    lines = [l.strip() for l in (text or "").split("\n") if l.strip()]
    out, i = [], 0
    short = lambda s: len(s) <= 50 and not re.search(r"[.:?!]$", s)
    while i < len(lines):
        line = lines[i]
        if line.startswith(("•", "- ")):
            out.append("- " + line.lstrip("•- ").strip())
        elif re.match(r"^\d+\.\s*\S", line):
            out.append(re.sub(r"^(\d+)\.\s*", r"\1. ", line))
        else:
            run = [line]
            while short(run[-1]) and i + 1 < len(lines) and short(lines[i + 1]):
                i += 1
                run.append(lines[i])
            if len(run) > 1:
                out.append("\n".join("- " + r for r in run))
            elif len(line) <= 60 and line.endswith((":", "?")):
                out.append(f"**{line}**")
            else:
                out.append(line)
        i += 1
    return re.sub(r"(\n?- [^\n]+)\n\n(?=- )", r"\1\n", "\n\n".join(out))     # keep list items together


def tags(items):
    return " · ".join(f"`{t}`" for t in items if t)


def excerpt(text, chars=280):
    text = " ".join(text.split())
    return text if len(text) <= chars else text[:chars].rsplit(" ", 1)[0] + " …"


def render(p):
    x = p.get("extra") or {}
    name = p.get("full_name") or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
    url = f"https://www.linkedin.com/in/{p['public_identifier']}/"
    md = []
    photo = x.get("profile_pic_file") or p.get("profile_pic_url")
    if photo:
        md.append(f'<img src="{photo}" alt="{name}" width="180" align="right">\n')
    md.append(f"# {name}\n")
    if p.get("headline"):
        md.append(f"**{p['headline']}**\n")
    place = ", ".join(v for v in (p.get("city"), p.get("state"), p.get("country_full_name")) if v)
    company = x.get("current_company") or (p.get("occupation") or "").split(" at ")[-1] if p.get("occupation") else x.get("current_company")
    people = " · ".join(v for v in (f"{p['follower_count']:,} followers" if p.get("follower_count") else "",
                                    (x.get("connections_text") or f"{p['connections']:,} connections") if p.get("connections") else "") if v)
    facts = [f"📍 {place}" if place else "", f"🏢 {company}" if company else "", f"👥 {people}" if people else "",
             f"🔗 [linkedin.com/in/{p['public_identifier']}]({url})"]
    md.append(" · ".join(f for f in facts if f) + "\n")
    md.append('<br clear="right">\n\n---\n')

    jobs = p.get("experiences") or []
    glance = []
    current = next((j for j in jobs if j.get("starts_at") and not j.get("ends_at")), None)
    if current:
        glance.append(("Current role", current["title"] + (f", {current['company']}" if current.get("company") else "")
                       + f" (since {when(current['starts_at'])})"))
    starts = [j["starts_at"]["year"] for j in jobs if j.get("starts_at")]
    if starts:
        glance.append(("Career on LinkedIn", f"{len(jobs)} roles since {min(starts)}"))
    top = x.get("top_skills") or (p.get("skills") or [])[:5]
    if top:
        glance.append(("Top skills", ", ".join(top)))
    recs = x.get("recommendations_detail") or p.get("recommendations") or []
    if recs:
        total = x.get("recommendations_received") or len(recs)
        glance.append(("Recommendations", f"{total} received ({len(recs)} below)"))
    if glance:
        md.append("## At a glance\n\n| | |\n|---|---|\n" + "\n".join(f"| **{k}** | {v} |" for k, v in glance) + "\n")

    def add(title, text):
        if text and text.strip():
            md.append(f"## {title}\n\n{text.strip()}\n")

    c = x.get("contact") or {}
    rows = [("Email", ", ".join(p.get("personal_emails") or [])), ("Phone", ", ".join(p.get("personal_numbers") or [])),
            ("Websites", ", ".join(c.get("Website", []) + c.get("Websites", []))), ("IM", ", ".join(c.get("IM", []))),
            ("Twitter", ", ".join(c.get("Twitter", []))), ("Address", ", ".join(c.get("Address", []))),
            ("Birthday", ", ".join(c.get("Birthday", []))), ("Connected since", ", ".join(c.get("Connected since", [])))]
    rows = [(k, v) for k, v in rows if v]
    if rows:
        md.append("## Contact\n\n| | |\n|---|---|\n" + "\n".join(f"| **{k}** | {v} |" for k, v in rows) + "\n")

    add("About", body(p.get("summary")))
    add("Services", tags(x.get("services", [])))

    parts = []
    for j in jobs:
        head = f"### {j.get('title') or ''}"
        if j.get("company"):
            head += f"\n**{j['company']}**" + (f" · {j['employment_type']}" if j.get("employment_type") else "")
        dates = f"{when(j['starts_at'])} – {when(j.get('ends_at'))}" if j.get("starts_at") else ""
        meta = " · ".join(v for v in (dates, length(j.get("starts_at"), j.get("ends_at")), j.get("location")) if v)
        part = head + (f"  \n*{meta}*" if meta else "")
        if j.get("description"):
            part += "\n\n" + body(j["description"])
        if j.get("skills"):
            part += "\n\nSkills: " + tags(j["skills"]) + (f" and {j['more_skills']} more" if j.get("more_skills") else "")
        parts.append(part)
    add("Experience", "\n\n".join(parts))

    edu = []
    for e in p.get("education") or []:
        degree = ", ".join(v for v in (e.get("degree_name"), e.get("field_of_study")) if v)
        years = " – ".join(dict.fromkeys(str(d["year"]) for d in (e.get("starts_at"), e.get("ends_at")) if d))
        edu.append(f"### {e.get('school')}" + (f"  \n{degree}" if degree else "") + (f"  \n*{years}*" if years else "")
                   + (f"\n\n{body(e['description'])}" if e.get("description") else ""))
    add("Education", "\n\n".join(edu))
    add("Licences & certifications", "\n".join(
        f"- **{c['name']}**" + "".join(f" — {v}" for v in (c.get("authority"),) if v)
        + (f" · issued {when(c['starts_at'])}" if c.get("starts_at") else "")
        + (f" · [credential]({c['url']})" if c.get("url") else "") for c in p.get("certifications") or []))
    add("Honours & awards", "\n".join(
        f"- **{a['title']}**" + (f" — {a['issuer']}" if a.get("issuer") else "")
        + (f" · {when(a['issued_on'])}" if a.get("issued_on") else "")
        + (f"  \n  {excerpt(a['description'])}" if a.get("description") else "") for a in p.get("accomplishment_honors_awards") or []))
    add("Projects", "\n".join(f"- **{pr['title']}**" + (f" — {excerpt(pr['description'])}" if pr.get("description") else "")
                              for pr in p.get("accomplishment_projects") or []))
    add("Publications", "\n".join(f"- **{pu['name']}**" + (f" — {pu['publisher']}" if pu.get("publisher") else "")
                                  + (f" · {when(pu['published_on'])}" if pu.get("published_on") else "")
                                  for pu in p.get("accomplishment_publications") or []))
    add("Volunteering", "\n".join(
        f"- **{v['title']}**" + (f", {v['company']}" if v.get("company") else "")
        + (f" · {when(v['starts_at'])} – {when(v.get('ends_at'))}" if v.get("starts_at") else "")
        + (f" · {v['cause']}" if v.get("cause") else "") for v in p.get("volunteer_work") or []))
    add("Organisations", "\n".join(
        f"- **{o['org_name']}**" + (f" — {o['title']}" if o.get("title") else "")
        + (f" · {when(o['starts_at'])} – {when(o.get('ends_at'))}" if o.get("starts_at") else "")
        for o in p.get("accomplishment_organisations") or []))
    add("Courses", tags(c["name"] for c in p.get("accomplishment_courses") or []))
    add("Languages", tags(p.get("languages") or []))

    endorse = x.get("skill_endorsements") or {}
    ranked = sorted(endorse.items(), key=lambda kv: -kv[1])
    others = [s for s in p.get("skills") or [] if s not in endorse]
    sk = []
    if ranked:
        cells = [f"**{n}** ({c})" for n, c in ranked] + [""] * (-len(ranked) % 3)
        sk.append("| | | |\n|---|---|---|\n" + "\n".join("| " + " | ".join(cells[i:i + 3]) + " |" for i in range(0, len(cells), 3)))
        sk.append("*Number of endorsements in brackets.*")
    if others:
        sk.append(("Also: " if ranked else "") + tags(others))
    add("Skills", "\n\n".join(sk))

    quotes = []
    for r in recs:
        if isinstance(r, str):                    # Proxycurl: "Name\n\n\n\nText"
            who, _, text = r.partition("\n\n\n\n")
            r = {"name": who.strip(), "text": text, "headline": "", "date": "", "relationship": ""}
        q = "\n>\n".join("> " + t for t in r["text"].split("\n\n") if t.strip()) + f"\n>\n> — **{r['name']}**"
        q += f", {r['headline']}" if r.get("headline") else ""
        meta = " · ".join(v for v in (r.get("date"), r.get("relationship")) if v)
        quotes.append(q + (f"  \n> <sub>{meta}</sub>" if meta else ""))
    add("Recommendations", "\n\n".join(quotes))

    def posts(items, n):
        return "\n".join(f"- {excerpt(i['text'])}" + (
            f"  \n  <sub>{' · '.join(v for v in (i.get('when'), i.get('stats')) if v)}</sub>" if i.get("when") or i.get("stats") else "")
            for i in items[:n])
    add("Featured", posts(x.get("featured", []), 3))
    if x.get("activity_posts"):
        add("Recent activity", posts(x["activity_posts"], 5))
    else:
        add("Recent activity", "\n".join(f"- {excerpt(a['title'])}  \n  <sub>{a.get('activity_status', '')}</sub>"
                                         for a in (p.get("activities") or [])[:5]))
    add("Articles", "\n".join(f"- [{a['title']}]({a['link']})" + (f" · {when(a['published_date'])}" if a.get("published_date") else "")
                              for a in p.get("articles") or []))
    interests = x.get("interests_detail") or [{"name": i, "type": "", "followers": ""} for i in p.get("interests") or []]
    add("Interests & causes", "\n\n".join(v for v in (
        "\n".join(f"- **{i['name']}**" + "".join(f" · {v}" for v in (i.get("type"), i.get("followers")) if v) for i in interests),
        ("Groups: " + tags(g["name"] for g in p.get("groups") or [])) if p.get("groups") and not x else "",
        ("Causes: " + tags(x["causes"])) if x.get("causes") else "") if v))
    src = f"Read from LinkedIn on {x['retrieved']} with browser_tool_call.py" if x.get("retrieved") else "From a Proxycurl profile export"
    md.append(f"---\n\n<sub>{src}. This is personal data: keep it private and delete it when you're done.</sub>\n")
    return "\n".join(md)


if __name__ == "__main__":
    args = sys.argv[1:]
    out_dir = Path(args[args.index("--out") + 1]) if "--out" in args else None
    files = [Path(a) for a in args if a.endswith(".json")]
    for src in files:
        profile = json.loads(src.read_text())
        if "sections" in profile:                        # raw browser data: convert, and keep the Proxycurl JSON
            profile = to_proxycurl(profile)
            src.write_text(json.dumps(profile, indent=2, ensure_ascii=False))
        target = (out_dir / src.with_suffix(".md").name) if out_dir else src.with_suffix(".md")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(profile))
        print(f"wrote {target}")
