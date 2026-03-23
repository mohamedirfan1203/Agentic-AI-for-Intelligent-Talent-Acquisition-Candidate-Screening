import os
import io
import fitz # PyMuPDF
import json
import logging
import re
import docx # python-docx
from datetime import datetime
from typing import Union, Any
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

INTERMEDIATE_DIR = "intermediate_data"

class IntelligentExtractor:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            logger.error("No GEMINI_API_KEY provided.")
            raise ValueError("No GEMINI_API_KEY provided.")
        
        # New Google GenAI SDK (Modern way)
        self.client = genai.Client(api_key=self.api_key)
        self.model_name = "gemini-2.5-flash"  # As requested
        logger.info(f"Modern Extractor ready with {self.model_name} (Word/PDF/TXT Mode)")
        
        # Ensure intermediate directory exists
        if not os.path.exists(INTERMEDIATE_DIR):
            os.makedirs(INTERMEDIATE_DIR)

    def extract_raw_text(self, file_content: bytes, filename: str) -> str:
        """Extracts text from PDF, DOCX, or TXT files."""
        logger.info(f"Extracting text from: {filename}")
        
        if filename.lower().endswith(".pdf"):
            try:
                doc = fitz.open(stream=file_content, filetype="pdf")
                return "".join([page.get_text() for page in doc]).strip()
            except Exception as e:
                logger.error(f"PyMuPDF error: {str(e)}")
                return ""
        
        elif filename.lower().endswith(".docx"):
            try:
                # docx requires a file-like object
                doc = docx.Document(io.BytesIO(file_content))
                return "\n".join([para.text for para in doc.paragraphs]).strip()
            except Exception as e:
                logger.error(f"python-docx error: {str(e)}")
                return ""
        
        elif filename.lower().endswith(".doc"):
            logger.warning(f"Detected legacy .doc format: {filename}. Please use .docx or .pdf for better results.")
            # We can try to cast it as text as a fallback, but it will likely produce garbage binary data.
            # Best to recommend .docx or .pdf for hackathon purposes.
            return ""

        elif filename.lower().endswith(".txt"):
            try:
                return file_content.decode("utf-8").strip()
            except UnicodeDecodeError:
                return file_content.decode("latin-1").strip()
        
        logger.warning(f"Unsupported file format attempted: {filename}")
        return ""

    def save_intermediate_json(self, data: dict, original_filename: str, doc_type: str):
        """Saves the extracted JSON to the intermediate_data folder."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = os.path.basename(original_filename).replace(".", "_")
            out_filename = f"{doc_type}_{safe_name}_{timestamp}.json"
            out_path = os.path.join(INTERMEDIATE_DIR, out_filename)
            
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            
            logger.info(f"Saved intermediate JSON to {out_path}")
            return out_path
        except Exception as e:
            logger.error(f"Failed to save intermediate JSON: {str(e)}")
            return None

    def parse_with_llm(self, raw_text: str, original_filename: str = "doc", doc_type: str = "resume") -> dict:
        """Parses raw text into a comprehensive dictionary using LLM."""
        logger.info(f"Parsing: {doc_type} using {self.model_name}")
        
        prompt = f"""
        Act as an expert HR Data Scientist. 
        Analyze the {doc_type} text below and extract EVERY piece of information into a highly detailed, structured JSON object.
        
        Instructions:
        1. Capture EVERYTHING: Skills, Experience, Projects, Awards, etc.
        2. Use professional and consistent keys.
        3. Return ONLY a valid JSON object.
        
        Text to Analyze:
        ---
        {raw_text}
        ---
        """

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
            
            data = json.loads(response.text)
            self.save_intermediate_json(data, original_filename, doc_type)
            return data
            
        except Exception as e:
            logger.error(f"LLM Error: {str(e)}")
            return {"error": "Parsing failed", "details": str(e)}

# Export singleton
extractor_service = IntelligentExtractor()
