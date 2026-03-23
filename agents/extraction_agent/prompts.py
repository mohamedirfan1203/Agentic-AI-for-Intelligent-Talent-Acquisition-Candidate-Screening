"""
LLM Prompt Templates for the Extraction Agent.
"""

RESUME_EXTRACTION_PROMPT = """
Act as an expert HR Data Scientist and Resume Parser.
Analyze the resume text below and extract EVERY piece of information into a
highly detailed, structured JSON object.

CRITICAL REQUIREMENTS:
1. The JSON response MUST start with these two fields at the top level:
   - "name": <candidate's full name as a string>
   - "email": <candidate's email address as a string>
   
   These fields are MANDATORY and must appear first in the JSON response.
   If name is not found, use "Unknown". If email is not found, use null.

2. After name and email, capture EVERYTHING else: Phone, Address, Skills (technical + soft),
   Work Experience (company, role, dates, responsibilities, achievements),
   Education (institution, degree, year), Projects, Certifications, Awards,
   Languages, and any other relevant fields.

3. Use professional and consistent snake_case keys.

4. If a field is not found, set it to null.

5. Return ONLY a valid JSON object — no markdown fences, no explanation.

Expected JSON Structure (name and email MUST be first):
{{
  "name": "Full Name Here",
  "email": "email@example.com",
  "phone": "...",
  "address": "...",
  ... (all other fields)
}}

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
