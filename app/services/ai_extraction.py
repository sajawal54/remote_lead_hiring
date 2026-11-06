import os
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import List

# Pydantic schema for structured output enforcement (PDF Section 4.7 & 8)
class ExtractedJobAttributes(BaseModel):
    skills: List[str] = Field(description="List of technical skills and tools extracted from job description")
    category: str = Field(description="Job service category e.g. Software Development, Data Engineering")
    seniority: str = Field(description="Seniority level e.g. Senior, Mid, Junior, Lead")
    remote_type: str = Field(description="Remote policy type e.g. fully-remote, hybrid, on-site")
    allowed_countries: List[str] = Field(description="Countries or regions where remote work is permitted, e.g. Global, US, Pakistan")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0 regarding the accuracy of extracted data",
    )

def extract_job_details_with_gemini(job_description: str) -> dict:
    """
    Calls Google Gemini API with structured output schema to extract 
    job attributes as specified in PDF Section 4.7 & 8.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {
            "status": "failed",
            "error": "GEMINI_API_KEY environment variable is missing.",
            "message": "AI extraction failed due to missing API key configuration."
        }

    try:
        # Initialize Gemini client
        client = genai.Client(api_key=api_key)
        
        prompt = f"""
        Analyze the following job description and extract the required attributes accurately.
        Job Description:
        {job_description}
        """

        # Call Gemini model with strict structured output enforcement
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ExtractedJobAttributes,
                temperature=0.1, # Low temperature for precise, deterministic extraction
            ),
        )

        # Parse the structured response back into dictionary
        extracted_data = ExtractedJobAttributes.model_validate_json(response.text).model_dump()

        return {
            "status": "success",
            "extraction": extracted_data,
            "model_version": "gemini-2.5-flash",
            "prompt_version": "v1.2"
        }

    except Exception as e:
        # PDF Section 10 & 8: Handling schema/API failures gracefully
        return {
            "status": "failed",
            "error": str(e),
            "message": "AI extraction failed during Gemini API call or schema validation."
        }