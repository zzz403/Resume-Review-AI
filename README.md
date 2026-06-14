# Focused Ultrasound Lab Application Review Tool

This program helps review high school summer program applications for the Focused Ultrasound Lab, specifically tuned for the Hynynen Lab application package. It extracts applicant information from uploaded application PDFs, Sunnybrook forms, resumes/CVs, cover letters, transcripts, STEM statements, and teacher evaluations, then writes the results into an Excel file for review.

The program is designed for the real application workflow, where applicants may upload documents in different orders or formats. The expected order is usually cover letter, resume/CV, Sunnybrook Focused Ultrasound Lab Summer Program form, and transcript, but the program does not depend only on that order. It searches for recognizable section content and form titles.

## How To Open The App

1. On Mac, double-click `start_app.command`.
2. On Windows, double-click `start_app.bat`.
3. Wait for the browser window to open.
4. If the browser does not open automatically, go to:

http://127.0.0.1:3000/

Keep the Terminal or Command Prompt window open while using the app. Closing it stops the app.

### Mac

1. Open the `Resume-Review-AI` folder.
2. Double-click `start_app.command`.

### Windows

1. Open the `Resume-Review-AI` folder.
2. Double-click `start_app.bat`.
3. Wait for the browser window to open.
4. If Windows asks for permission, choose to allow it.
5. If the browser does not open automatically, go to:

http://127.0.0.1:3000/

## How To Use The App

When the app opens, the first page is the `Students` roster for `Hynynen Lab · Applicant Review`. Use this page to add candidates, open existing profiles, search the roster, and see each candidate's review status.

### 1. Set Up AI Keys

1. Open `Settings`.
2. Choose a provider for `Text AI`.
3. Paste the matching API key and click `Save`.
4. If you want image reading for scanned forms, choose a provider under `Image Reading AI`, paste that key, and click `Save`.

OpenAI/ChatGPT, Anthropic/Claude, and Google Gemini can be used for image reading. DeepSeek can be used for text scoring, but not for image reading.

### 2. Add A Candidate

1. Type the applicant's name into `New student name`.
2. Click `+ New Student`.
3. If a candidate with the same name already exists, choose either `Open existing profile` or `Add as new candidate`.

The `+ New Student` button stays disabled until a name is entered. This prevents empty student records.

### 3. Upload Files

1. Open the candidate profile from the roster.
2. Upload the main application package into `Application`.
3. Upload the teacher reference form into `Teacher Evaluation`.
4. Wait until the processing indicator finishes.

The application package usually includes the cover letter, resume/CV, Sunnybrook form, transcript, and STEM statement.

### 4. Review Results

After processing, the candidate profile shows extracted application fields, teacher evaluation fields, notes, and scores. The roster also shows a summary of each candidate, including school, grade, status, resume score, cover letter score, STEM statement score, teacher score, and academic ranking.

### 5. Manually Correct Fields

Use `Edit & review` to compare extracted fields against the source PDF and manually correct saved values. Save changes before returning to the roster or exporting the spreadsheet.

### 6. Export Or Reset

Use `Download xlsx` to export the current spreadsheet. Use `Settings` > `Reset all saved data` only when starting a new application cycle.

See `Main Output` for where exported data is stored, and `Resetting Data` for exactly what reset deletes.

### Image Reading Notes

The app can use image-reading AI for scanned forms, handwritten teacher evaluations, checkbox rankings, and hard-to-read PDF pages. Clear typed PDFs still use normal extraction first because it is faster and cheaper.

When key fields are missing or suspicious, upload the file again after saving a valid image-reading API key.

## Extraction Method

- The program first tries normal PDF or DOCX text extraction.
- For scanned/image-based PDF pages, the program uses OCR.
- OCR uses high-resolution PDF rendering and `pytesseract`.
- OCR can help with scanned forms, but handwritten text is still less reliable than typed text.
- For teacher evaluation checkboxes, the program can use visual checkbox detection when text extraction does not clearly show the selected ranking.
- For some scanned or handwritten application and teacher evaluation fields, the program can use AI vision if a vision-capable AI provider key is configured.
- If a field cannot be read reliably, the program leaves the value blank and writes a note in the relevant note column.
- AI is used when available for more flexible summary/evaluation tasks, such as resume feature summaries, STEM statement scoring, career goals, previous research experience, and teacher comment summaries.
- If the API key is missing or invalid, the program falls back to rule-based or text-based extraction where possible.

## Main Output

- Results are saved to:
  - `backend/data/applications.xlsx`
  - `backend/data/applications.json`
- The Excel file contains one row per applicant.
- Application uploads and teacher evaluation uploads are matched mainly by applicant name or email.
- Teacher evaluations can be uploaded separately and later merged into the matching applicant row.

## General Application Notes

- `General Application Note`
  - Records missing or unclear application sections and whether the teacher evaluation is missing.
  - This column is for application-structure problems, not detailed form-reading problems.
  - It is empty when no general application issue is detected and the teacher evaluation has been uploaded.
  - It may mention:
    - Sunnybrook application form was not clearly detected
    - transcript section was not clearly detected
    - cover letter section was not confidently detected
    - resume/CV section was not confidently detected
    - teacher evaluation is missing

## Application Identity Columns

- `applicant_name`
  - Collects the applicant's name.
  - Main source: Sunnybrook form `Full Name`.
  - Fallback source: filename or early text in the document.

- `email`
  - Collects the applicant's email address.
  - Source: the full application PDF.
  - Method: searches for the first email-format text.

- `school`
  - Collects the applicant's current high school.
  - Main source: Sunnybrook form field `Current High School (please include city)`.
  - Fallback source: resume or transcript-like school text.

- `city`
  - Collects the school/applicant city when available.
  - Main source: the Sunnybrook school field.
  - Method: looks for city patterns such as `City, ON` or `City, Ontario`.

- `current_grade`
  - Collects the applicant's current grade.
  - Main source: Sunnybrook form `Current Grade`.
  - Fallback source: inferred from form grades or course codes.

- `gender`
  - Collects an inferred gender only when clear.
  - Source: teacher evaluation comments.
  - Method: uses repeated teacher pronouns such as `he/him/his` or `she/her`.
  - If pronouns are unclear or mixed, the column stays blank.

## Sunnybrook Form Columns

- `experimental_work_rank`
  - Collects the applicant's rank for Experimental Work.
  - Source: Sunnybrook form project preference section.
  - Method: reads PDF annotations/free-text values or OCR/text near the project label.

- `engineering_technology_development_rank`
  - Collects the applicant's rank for Engineering and Technology Development.
  - Source: Sunnybrook form project preference section.
  - Method: same as above.

- `programming_rank`
  - Collects the applicant's rank for Programming.
  - Source: Sunnybrook form project preference section.
  - Method: same as above.

- `Sunnybrook Form Note`
  - Records Sunnybrook-form-specific reading problems.
  - This column is empty when no form-specific issue is detected.
  - It may mention:
    - full name could not be read from the form
    - current high school could not be read from the form
    - current grade could not be read from the form
    - academic grades could not be read from the form
    - specific project preference ranks could not be read
    - the STEM / `More about the Applicant` answer could not be read

## Cover Letter Columns

- `cover_letter_rating_10`
  - Scores the cover letter out of 10.
  - Source: detected cover letter section.
  - Method: uses AI if available; otherwise uses a fallback rubric.
  - AI rubric:
    - Scores the same general criteria as the fallback rubric, but asks the AI to judge the letter more flexibly.
    - Criteria include a strong opening explaining why the applicant wants the role, relevant skills/experience, concrete accomplishments, quantified impact, call to action, formal closing, professional brief format with contact information, named addressee, personalization to the organization/program, and FUS lab relevance.
    - To score 8-10, the letter must show some understanding of what the FUS lab does. Examples include focused ultrasound research, non-invasive therapy/treatment, biomedical imaging, device/technology development, brain or cancer applications, experimental work, MRI guidance, ablation, drug delivery, nanoparticles, microbubbles, sonodynamic therapy, neurostimulation, or other specific lab-relevant work.
    - If the letter mentions the program but does not show what the FUS lab does, the maximum score is 7.
    - If the letter does not reference the FUS lab/program at all, the maximum score is 6.
  - Fallback rubric, used when AI is unavailable:
    - 1 point for an opening that shows interest in the opportunity.
    - 1 point for relevant skills or experience.
    - 1 point for examples or accomplishments.
    - 1 point for quantified impact, such as a number of students, people, patients, projects, hours, weeks, months, years, members, or participants.
    - 1 point for a closing call to action.
    - 1 point for a formal closing, such as `sincerely`, `regards`, or `thank you`.
    - 1 point for professional brief format with contact information.
    - 1 point for addressing a named reader.
    - 1 point for personalization to Sunnybrook, FUS, Focused Ultrasound, or the research program.
    - 1 point for showing understanding of FUS lab work.
    - If the applicant references the program but does not show FUS understanding, the fallback score is capped at 7.
    - If the applicant does not reference the program, the fallback score is capped at 6.

- `Reference to FUS`
  - Records whether the applicant mentions focused ultrasound/FUS.
  - Source: cover letter and STEM statement.
  - Method: searches for terms such as `focused ultrasound`, `FUS`, and `ultrasound`.

- `fus_understanding_summary`
  - Summarizes whether the applicant shows understanding of FUS.
  - Source: cover letter and STEM statement.
  - Method: checks whether the applicant uses lab-relevant concept categories such as non-invasive treatment, imaging/guidance, MRI, biomedical/medical or clinical application, device/technology development, acoustics/sonication, sonodynamic therapy, brain/neuroscience application, neurostimulation, cancer/tumor application, drug delivery, nanoparticles, microbubbles, or preclinical/experimental research.

- `FUS Understanding Rate (/5)`
  - Rates the applicant's FUS understanding.
  - Source: cover letter and STEM statement.
  - Method: counts distinct FUS-relevant concept categories after confirming that FUS/focused ultrasound/ultrasound is mentioned.
  - Rating logic:
    - 0 if FUS/focused ultrasound/ultrasound is not clearly mentioned
    - 1 if FUS is mentioned but no relevant concept category is detected
    - 2 if 1 relevant concept category is detected
    - 3 if 2 relevant concept categories are detected
    - 4 if 3 relevant concept categories are detected
    - 5 if 4 or more relevant concept categories are detected

## Resume/CV Columns

- `resume_rating_10`
  - Scores the resume out of 10.
  - Source: detected resume/CV section.
  - Method: rule-based resume rubric.
  - Rating scale:
    - Experience is worth up to 3 points.
      - 0 points if relevant work, volunteering, internship, tutoring, or assistant experience is not clearly listed.
      - 1 point if experience is present.
      - 1 additional point if the experience includes useful action/detail, such as developed, facilitated, assisted, organized, collaborated, supported, helped, promoted, or quantified impact.
      - 1 additional point if the experience has FUS/lab/biomedical relevance, such as focused ultrasound, ultrasound, biomedical imaging, medical device, device development, non-invasive technology, acoustics, transducers, lab research, research assistant, or research intern.
    - Education is worth up to 1 point.
      - 1 point if education is clearly listed with terms such as `High School Diploma`, `Secondary School`, `Education`, or `Expected in`.
    - Skills are worth up to 2 points.
      - 0 points if no skills section or relevant skills are clearly detected.
      - 1 point if skills are present but generic or weakly connected to the program.
      - 2 points if at least 3 relevant skill terms are found, such as biology, chemistry, physics, computer, programming, problem-solving, critical thinking, communication, teamwork, or OCRA.
    - Awards/accomplishments/certifications are worth up to 1 point.
      - 1 point if relevant awards, accomplishments, certifications, certificates, OCRA, or science/math/biology/chemistry/physics-related achievements are clearly listed.
    - Format and conciseness are worth up to 3 points.
      - 3 points for a plain, simple, likely one-page resume.
      - 2 points for an acceptable resume that could be cleaner or more concise.
      - 1 point for a weak format.
      - 0 points if the resume appears to be more than one page or has too many bullet points under one experience.
    - The final score is capped at 10.

- `features`
  - Summarizes STEM-relevant resume features.
  - Source: resume/CV, with STEM statement used as extra context if useful.
  - Method: uses AI if available; otherwise uses text-based fallback.
  - It focuses on concrete evidence of what the applicant did, not isolated keywords.
  - It can include:
    - programming
    - engineering
    - robotics
    - research
    - lab/science work
    - health or clinical experience
    - hospital or patient-facing work
    - STEM tutoring
    - certifications
    - STEM-related projects
    - STEM-related leadership
  - The summary is intended to stay concise, usually under 100 words.

- `volunteer_experience`
  - Records whether volunteering is detected.
  - Source: full application.
  - Method: looks for volunteer/community involvement terms.

- `previous_research_experience`
  - Records whether the applicant appears to have previous research experience.
  - Source: resume/CV and STEM statement.
  - Method: uses AI if available; otherwise checks for strong evidence such as:
    - research assistant
    - research intern
    - lab research
    - independent research project
    - science fair research
    - publication
    - poster presentation
  - It does not count generic interest in research by itself.

## STEM Statement Columns

- `career_goals`
  - Collects the applicant's career goal.
  - Source: STEM statement / `More about the Applicant` section.
  - Method: uses AI if available; otherwise looks for aspiration, career, goal, or future-intent sentences.

- `stem_statement_rating_10`
  - Scores the STEM statement out of 10.
  - Source: Sunnybrook form `More about the Applicant` / STEM statement.
  - Method: uses AI if available; otherwise uses a fallback rubric.
  - Criteria include:
    - what the applicant aspires to be or do
    - what motivates them to get involved in STEM
    - why they are a valuable candidate
    - specificity and concrete examples
    - FUS/lab relevance or passion
  - Important scoring caps:
    - If there is no clear FUS/lab relevance, the score is capped.
    - If FUS is only named without explanation, the score is capped.
    - If one required question is missing, the score is capped.
    - If the statement is mostly generic traits without evidence, the score is capped.

- `commitment_to_stem`
  - Summarizes the applicant's demonstrated commitment to STEM.
  - Source: resume/CV and STEM statement.
  - Method: summarizes STEM-related experience, awards, and motivation.
  - It does not include the opening coursework/grade sentence.

## Transcript and Grade Columns

- `transcript_relative_to_class_median_5`
  - Gives an academic strength rating out of 5.
  - Main source: Sunnybrook form academic grades.
  - Fallback source: transcript.
  - Method: averages math, science, and English-related course marks.
  - Rating logic:
    - average above 90 gives 5
    - average 85-90 gives 4
    - average 75-84 gives 3
    - average 65-74 gives 2
    - average below 65 gives 1

- `lowest_grade_in_current_grade`
  - Records the lowest course mark in the applicant's current grade.
  - Main source: Sunnybrook form academic grades.
  - Fallback source: transcript.
  - Method: identifies courses from the current grade and stores the lowest percentage.

## Teacher Evaluation Columns

- `Teacher's Report`
  - Collects the teacher evaluation score as a rating out of 5.
  - Source: teacher evaluation form.
  - Method:
    - reads `Total Score: __ /50`
    - converts it to a `/5` rating
    - example: `48/50` becomes `4.8`
  - For some forms where answers are appended after the blank template, the program uses a fallback answer-order parser.
  - For scanned/handwritten scores, AI vision may be used if available.

- `Teacher Evaluation Note`
  - Records teacher-evaluation-specific reading problems.
  - This column is empty when no teacher evaluation issue is detected.
  - It may mention:
    - teacher rating could not be read
    - academic ranking could not be read
    - teacher comments could not be read
    - teacher rating was read from handwriting/scanned form and should be verified manually
    - manual review is recommended for scanned/handwritten teacher evaluations

- `Comments`
  - Summarizes teacher comments and reference letters.
  - Source: teacher evaluation comments section, attached/reference letter text if included in the same PDF, and improvement-area section.
  - Method: uses AI if available.
  - The AI summary is designed to include whatever the teacher says, positive or negative, including strengths, concerns, and improvement areas.
  - If AI is not available, the fallback may use extracted sentences from the teacher text and will be less polished than a true summary.

- `Academic Ranking`
  - Collects the teacher's academic ranking selection.
  - Source: teacher evaluation form.
  - Method:
    - reads marked text when available
    - checks for `Top 5%`, `Top 10%`, `Top 15%`, `Top 20%`, or `Top 25%`
    - uses visual checkbox detection when text extraction does not clearly identify the selected option

## Review Guidance

- Blank cells usually mean the program could not confidently extract that field.
- Read `General Application Note` first to see if a whole application section or teacher evaluation is missing.
- Read `Sunnybrook Form Note` to see if a specific Sunnybrook form field failed.
- Read `Teacher Evaluation Note` to see if a teacher evaluation field failed.
- For scanned or handwritten submissions, manually verify important values such as project ranks, grades, teacher score, academic ranking, and comments.
- AI-generated summaries and ratings should support human review, not replace final reviewer judgment.

## Resetting Data

- Use `Reset Saved Data` on the frontend to start a new application cycle.
- The button clears:
  - saved Excel rows
  - saved JSON rows
  - saved teacher evaluation PDFs
  - temporary Excel lock file, if present
- It does not delete the program code, `.env`, dependencies, or README.
- The button asks for confirmation before deleting data.

## Basic Setup

- The frontend includes an `Anthropic API Key` box.
- Paste the lab manager's Anthropic API key there and click `Save Key`.
- The program checks whether the key is valid before saving it.
- If the key is valid, it is saved to the local `.env` file.
- If the key is invalid, the frontend shows an error and does not save it.
- The key should start with `sk-ant-`.
- You can also create or edit `.env` manually:

```bash
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

- Start the backend:

```bash
cd backend
source venv/bin/activate
uvicorn main:app --host 127.0.0.1 --port 8000
```

- Start the frontend:

```bash
cd frontend
npm run dev
```

- Open the frontend in your browser:

```text
http://localhost:3000
```
