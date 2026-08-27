"""
gradebook_exporter.py
---------------------
Handles exporting gradebook data to CSV and Excel format.
"""
import csv
import io
import pandas as pd
from database import get_gradebook_data

def export_csv(subject_slug):
    data = get_gradebook_data(subject_slug)
    
    # Create an in-memory string buffer
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(["Student Name", "Roll No", "Timestamp", "Score", "Max Marks", "Grade", "Pass/Fail"])
    
    for row in data:
        status = "Pass" if row["passed"] else "Fail"
        cw.writerow([
            row["student_name"], 
            row["roll_no"], 
            row["timestamp"], 
            row["total_score"], 
            row["max_marks"], 
            row["grade"], 
            status
        ])
        
    return si.getvalue()


def export_xlsx(subject_slug):
    data = get_gradebook_data(subject_slug)
    
    # Format data for pandas
    formatted_data = []
    for row in data:
        status = "Pass" if row["passed"] else "Fail"
        formatted_data.append({
            "Student Name": row["student_name"],
            "Roll No": row["roll_no"],
            "Date": row["timestamp"],
            "Score": row["total_score"],
            "Max Marks": row["max_marks"],
            "Grade": row["grade"],
            "Status": status
        })
        
    df = pd.DataFrame(formatted_data)
    if df.empty:
        # Create empty dataframe with columns if no data
        df = pd.DataFrame(columns=["Student Name", "Roll No", "Date", "Score", "Max Marks", "Grade", "Status"])
        
    # Create an in-memory bytes buffer
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name="Gradebook")
        
    return output.getvalue()
