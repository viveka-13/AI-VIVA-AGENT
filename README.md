# AI Viva Agent

An AI-powered academic platform that automates the oral examination (viva) process for students, featuring local AI processing, Voice/TTS integration, and a Faculty Portal for dynamic question generation.

## 🌟 Features

*   **Student Portal**: Students enter their details, select a subject, and answer automatically generated questions. Features Text-To-Speech (TTS) voice announcements and a sleek cyber-aesthetic UI.
*   **Faculty Portal**: Instructors can register, manage subjects, and upload study materials (`.pdf`, `.pptx`, `.docx`, `.txt`).
*   **AI Question Generation**: Automatically extracts text from uploaded materials and generates Q&A pairs using local **Ollama** LLM processing (no external API keys required).
*   **AI Answer Evaluation**: The system evaluates student answers using local LLM inference to determine if they are Correct, Partially Correct, or Incorrect, then generates a final grade report.

## 🛠️ Prerequisites

1.  **Python 3.8+**
2.  **Ollama**: You must have Ollama installed on your machine to run the local AI model.
    *   Download from [Ollama.com](https://ollama.com/)
    *   Once installed, open your terminal and run: `ollama pull llama3.2`

## 🚀 Installation & Setup

1.  **Clone the repository**
    ```bash
    git clone https://github.com/your-username/AI-VIVA-AGENT.git
    cd AI-VIVA-AGENT
    ```

2.  **Install Python dependencies**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Run the application**
    ```bash
    python app.py
    ```

4.  **Access the web app**
    *   Student Portal: `http://127.0.0.1:5000/`
    *   Faculty Portal: `http://127.0.0.1:5000/faculty`

## 📁 Project Structure

*   `app.py`: Main Flask application router.
*   `Laptop2.py`: Orchestrates loading and serving the questions.
*   `llm_check.py` / `evaluation.py`: Handles the Ollama AI evaluation logic.
*   `question_generator.py`: Generates the dynamic question banks from uploaded faculty materials.
*   `file_extractor.py`: Utility to parse text out of PDFs, PPTXs, and DOCX files.
*   `templates/`: HTML templates for the UI.
*   `faculty_data/`: Automatically generated folder where uploaded materials and subject questions are locally stored.

## 📝 License
This project is open-source and available under the MIT License.
