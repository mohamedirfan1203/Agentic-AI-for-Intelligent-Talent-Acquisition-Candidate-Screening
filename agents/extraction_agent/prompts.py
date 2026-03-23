"""
LLM Prompt Templates for the Extraction Agent.
"""

RESUME_EXTRACTION_PROMPT = """
Act as an expert HR Data Scientist and Resume Parser.
Analyze the resume text below and extract EVERY piece of information into a
highly detailed, structured JSON object.

Instructions:
1. Capture EVERYTHING: Full Name, Email, Phone, Address, Skills (technical + soft),
   Work Experience (company, role, dates, responsibilities, achievements),
   Education (institution, degree, year), Projects, Certifications, Awards,
   Languages, and any other relevant fields.
2. Use professional and consistent snake_case keys.
3. If a field is not found, set it to null.
4. Return ONLY a valid JSON object — no markdown fences, no explanation.

Resume Text to Analyze:
---
{raw_text}
---
"""

JD_EXTRACTION_PROMPT = """
Act as an expert HR Data Scientist and Job Description Analyst.
Analyze the job description text below and extract EVERY piece of information
into a highly detailed, structured JSON object.

Instructions:
1. Capture ALL details: Job Title, Company Name, Location, Employment Type,
   Required Skills, Preferred Skills, Years of Experience, Responsibilities,
   Key Competencies, Educational Requirements, Salary Range (if mentioned),
   Benefits (if mentioned), and any other relevant fields.
2. Use professional and consistent snake_case keys.
3. If a field is not found, set it to null.
4. Return ONLY a valid JSON object — no markdown fences, no explanation.

Job Description Text to Analyze:
---
{raw_text}
---
"""
