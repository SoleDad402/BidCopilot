"""LLM prompt templates for job matching."""

SCORING_PROMPT = """You are a job matching analyst. Score how well this job matches the candidate.
Be critical — false positives waste the candidate's time and daily application quota.

## Candidate Profile
{profile_summary}

## Job Posting
- Title: {job_title}
- Company: {job_company}
- Location: {job_location}
- Remote: {job_remote}
- Salary: {job_salary}

### Full Description
{job_description}

## Score each dimension 0-100:
- skill_match: Overlap between required skills and candidate skills. Required > nice-to-have.
- seniority_fit: Level match? Penalize if over/under-qualified by >1 level.
- culture_signals: Remote alignment, company size, industry fit, company reputation.
- compensation_fit: If salary listed, compare to candidate minimum. If unlisted, estimate.
- overall_score: Weighted average (skill 40%, seniority 25%, culture 15%, comp 20%).
- red_flags: List any concerns (unrealistic reqs, scam indicators, toxic signals, etc.)
- reasoning: 2-3 sentences explaining the score.

Respond as JSON with keys: skill_match, seniority_fit, culture_signals, compensation_fit, overall_score, red_flags (list of strings), reasoning (string)."""

FORM_FILL_PROMPT = """You are filling out a job application form. Map each field to the best value.

## Form Fields
{fields_json}

## Candidate Profile
{profile}

## Job Details
Title: {job_title} at {company}
Description (excerpt): {job_description}

## Candidate Resume (excerpt)
{resume_text}

## Rules:
- For name fields: use the candidate's actual name
- For email: use candidate's email
- For phone: use candidate's phone in the format the placeholder suggests
- For "years of experience": calculate from work history
- For salary expectation: use candidate's min_salary
- For open-ended questions (textarea): write thoughtful 2-4 sentence answers highlighting relevant experience
- For select/radio: pick the closest matching option from the available options
- For fields you cannot determine: return "NEEDS_HUMAN_INPUT"
- For file upload fields: return "SKIP" (handled separately)

Return a JSON mapping of field_id → value."""

QUESTION_ANSWER_PROMPT = """Answer this job application question convincingly and concisely (2-4 sentences).

Question: {question}

Context:
- Applying for: {job_title} at {company}
- Job description excerpt: {job_description}
- Candidate skills: {skills}
- Candidate experience: {years_experience} years
- Current role: {current_title}

Guidelines:
- Be specific, reference relevant skills/experience from the candidate's background
- Show genuine interest in the company's work (reference details from JD)
- Keep it professional but personable
- Don't be generic — tailor to this specific role and company"""

SKILL_EXTRACT_PROMPT = """Extract technical skills and requirements from this job description.

Job Description:
{job_description}

Return JSON with:
- required_skills: list of explicitly required skills/technologies
- nice_to_have_skills: list of preferred/bonus skills
- seniority_level: one of "junior", "mid", "senior", "staff", "principal", "lead", "manager"
- remote_type: one of "remote", "hybrid", "onsite", "unknown"
- salary_min: integer or null
- salary_max: integer or null"""
