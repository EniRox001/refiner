from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
import PyPDF2
import docx
import requests
import json
from typing import Optional
import io
import re
import ast

app = FastAPI(title="Resume Job Description Matcher")

def extract_text_from_file(file: UploadFile) -> str:
    """
    Extract text from various file types (PDF, DOCX, TXT)
    
    Args:
        file (UploadFile): Uploaded file
    
    Returns:
        str: Extracted text from the file
    """
    try:
        # Read file content
        content = file.file.read()
        
        # Determine file type and extract text
        if file.filename.lower().endswith('.pdf'):
            # PDF extraction
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
            text = ' '.join([page.extract_text() for page in pdf_reader.pages])
        
        elif file.filename.lower().endswith('.docx'):
            # DOCX extraction
            docx_file = docx.Document(io.BytesIO(content))
            text = ' '.join([para.text for para in docx_file.paragraphs if para.text])
        
        elif file.filename.lower().endswith('.txt'):
            # TXT extraction
            text = content.decode('utf-8')
        
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type")
        
        return text
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error extracting text: {str(e)}")

def convert_to_single_string(text: str) -> str:
    """
    Convert text to a single string by removing newlines and extra spaces
    
    Args:
        text (str): Input text
    
    Returns:
        str: Cleaned single-line string
    """
    # Remove newlines, replace with spaces, and collapse multiple spaces
    return ' '.join(text.split())
def clean_json_string(json_string):
    """
    Clean and parse JSON string with comprehensive parsing techniques
    
    Args:
        json_string (str): Input JSON-like string
    
    Returns:
        dict: Fully parsed and cleaned JSON dictionary
    """
    def convert_to_snake_case(obj):
        """Recursively convert dictionary keys to snake_case"""
        if isinstance(obj, dict):
            return {
                re.sub(r'(?<!^)(?=[A-Z])', '_', k).lower(): 
                convert_to_snake_case(v) for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [convert_to_snake_case(item) for item in obj]
        return obj

    # Remove Markdown code block if present
    if json_string.strip().startswith("```") and json_string.strip().endswith("```"):
        json_string = re.sub(r"^```.*?\n|```$", "", json_string.strip(), flags=re.S)

    # List of parsing attempts with increasing aggressiveness
    parsing_attempts = [
        lambda s: json.loads(s),  # Direct parsing
        lambda s: json.loads(re.sub(r'\\n\s*', '', s)),  # Remove escaped newlines
        lambda s: json.loads(s.replace('\\"', '"').replace('\\n', ' ')),  # Replace escapes
        lambda s: json.loads(re.sub(r'\\["\'ntr]', ' ', s)),  # Aggressive cleaning
        lambda s: ast.literal_eval(s)  # Use ast.literal_eval
    ]

    # Try different parsing methods
    for attempt in parsing_attempts:
        try:
            # Parse the JSON
            parsed_json = attempt(json_string)
            
            # Convert to snake_case
            cleaned_json = convert_to_snake_case(parsed_json)
            
            return cleaned_json
        except (json.JSONDecodeError, SyntaxError) as e:
            continue

    # If all parsing methods fail
    return {
        "error": "Failed to parse JSON",
        "original_string": json_string,
        "error_details": "All parsing attempts failed"
    }

@app.post("/match-resume")
async def match_resume(
    resume: UploadFile = File(...), 
    job_description: str = "",
    experience_level: str = ""
):
    """
    Process resume and job description, then make an AI matching request
    
    Args:
        resume (UploadFile): Resume file
        job_description (str): Job description text
        experience_level (str): Experience level text
    
    Returns:
        JSONResponse with matching results
    """
    try:
        # Extract text from resume
        resume_text = extract_text_from_file(resume)
        resume_string = convert_to_single_string(resume_text)
        
        # Prepare payload for matching service
        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": """You are a professional resume analysis AI. Your task is to provide a comprehensive JSON analysis of the resume. 

        OUTPUT INSTRUCTIONS:
        1. Return ONLY a valid, well-formatted JSON object
        2. Use snake_case for all keys
        3. Ensure all sections are present and filled with appropriate data
        4. Do not include any text outside of the JSON
        5. Format should exactly match this structure and fill all with proper data:
        {
            "document_name": "Candidate Name Resume",
            "overall_readiness": {
                "percentage_score": 0,
                "executive_summary": "Concise professional summary "
            },
            "structural_analysis": {
                "critical_feedback": "Structural insights to improve for role job description",
                "scores": {
                    "formatting_out_of_hundred": 0,
                    "readability_out_of_hundred": 0,
                    "section_organization_out_of_hundred": 0
                }
            },
            "content_review": {
                "insights": "Content evaluation",
                "strengths_and_improvements": "Specific recommendations to make more fitting for role"
            },
            "skills_evaluation": {
                "required_skills_count_out_of_ten": 0,
                "skill_insights": "Detailed skills analysis in respect to job description"
            },
            "keyword_analysis": {
                "match_percentage_out_of_hundred": 0,
                "keyword_insights": "Keyword matching details in respect to job description"
            },
            "solution": "Comprehensive improvement recommendations"
        }

        Analyze the resume thoroughly and provide precise, actionable insights make it a little verbose though."""
                },
                {
                    "role": "user",
                    "content": f"Resume Text: {resume_string}. Job Description: {job_description}, Experience Level: {experience_level}"
                }
            ]
        }

        # Make request to local matching service
        response = requests.post(
            "https://0x6914a3acd0536c97afc26e3139d0ca1b75f154b2.us.gaianet.network/v1/chat/completions",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=10000,
        )

        # Parse the response
        response_json = response.json()
        
        # Extract the content from the first choice
        match_result = response_json.get('choices', [{}])[0].get('message', {}).get('content', '{}')
        
        # Clean and parse the JSON
        result_json = clean_json_string(match_result)

        return JSONResponse(content=result_json)
    
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
