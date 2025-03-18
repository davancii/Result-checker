import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime
from dotenv import load_dotenv
import platform
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import json

load_dotenv()

def format_results(json_response, group_name=None):
    details = f"""
    معلومات الطالب:
    ═══════════════
    الاسم: {json_response.get('student_name')}
    رقم الطالب: {json_response.get('student_number')}
    الكلية: {json_response.get('faculty')}
    البرنامج: {json_response.get('program')}
    الفرقة: {json_response.get('group')}
    المجموعة: {group_name}
    نوع الدراسة: {json_response.get('study_type')}
    الفصل الدراسي: {json_response.get('semester')}

    النتائج:
    ═══════
    """
    
    # Add subject results
    subjects = json_response.get('result_subjects_details', [])
    for subject in subjects:
        subject_name = subject.get('subject_name', '')
        subject_type = subject.get('subject_type', '')
        grade = subject.get('0', [{}])[0].get('column_value', '').strip()
        
        if grade and grade != '-\n':
            details += f"\n{subject_name} ({subject_type}):"
            details += f"\n    التقدير: {grade}"
            details += "\n─────────────────────"
    
    return details

def get_all_groups(session, url, headers, csrf_token, faculty_id):
    try:
        # Set up data for groups request
        data = {
            'exam_year_id': '1',
            'faculty_id': faculty_id,
            '_token': csrf_token
        }
        
        # Make the POST request to get groups
        groups_url = "https://services.aun.edu.eg/results/public/ar/filter_groups/ajax"
        response = session.post(groups_url, data=data, headers=headers)
        response.raise_for_status()
        
        # Parse the JSON response
        json_data = response.json()
        
        # Extract groups from the faculty_groups array
        groups = []
        if json_data.get('status') == True and 'faculty_groups' in json_data:
            for group in json_data['faculty_groups']:
                groups.append({
                    'id': str(group['id']),
                    'name': group['name']
                })
        
        print(f"Found {len(groups)} groups:")
        for group in groups:
            print(f"  - {group['name']} (ID: {group['id']})")
            
        return groups
    except Exception as e:
        print(f"Error in fetching groups: {str(e)}")
        print(f"Response content: {response.text}")  # Print response content on error
        return []

def check_exam_results(student_id, faculty_id):
    try:
        url = "https://services.aun.edu.eg/results/public/ar/exam-result"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept-Language': 'ar,en-US;q=0.9,en;q=0.8',
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-Requested-With': 'XMLHttpRequest',
            'Connection': 'keep-alive',
            'Origin': 'https://services.aun.edu.eg',
        }
        
        # Create session and get CSRF token
        session = requests.Session()
        initial_response = session.get(url, headers=headers)
        initial_response.raise_for_status()
        
        soup = BeautifulSoup(initial_response.text, 'html.parser')
        csrf_token = soup.find('meta', {'name': 'csrf-token'})['content']
        
        headers['X-CSRF-TOKEN'] = csrf_token
        headers['Referer'] = url
        
        # Get all available groups
        groups = get_all_groups(session, url, headers, csrf_token, faculty_id)
        print(f"Found {len(groups)} Groups")
        
        # Try each group
        for group in groups:
            print(f"\nChecking group: {group['name']} (ID: {group['id']})")
            
            data = {
                '_token': csrf_token,
                'exam_year_id': '1',
                'faculty_id': faculty_id,
                'group_id': group['id'],
                'department_id': '',
                'division_id': '',
                'student_name_number': student_id
            }
            
            try:
                response = session.post(url, data=data, headers=headers)
                response.raise_for_status()
                
                # Print raw response for debugging
                print(f"Raw response for group {group['id']}: {response.text[:200]}...")
                
                # Check if response is empty
                if not response.text:
                    print(f"Empty response for group {group['id']}")
                    continue
                
                json_response = response.json()
                print(f"Response status for group {group['id']}: {json_response.get('status')}")
                
                # Check if results found
                if json_response.get('status') == 'true' and (
                    json_response.get('student_name') == student_id or 
                    json_response.get('student_number') == student_id
                ):
                    print(f"Exam results found at group : {group['name']}")
                    formatted_results = format_results(json_response, group['name'])
                    return True, formatted_results, group['name']
                    
            except requests.exceptions.RequestException as e:
                print(f"Error making request for group {group['id']}: {str(e)}")
                continue
            except json.JSONDecodeError as e:
                print(f"Error parsing JSON for group {group['id']}: {str(e)}")
                print(f"Response content: {response.text}")
                continue
                
            # Small delay between requests to avoid overwhelming the server
            time.sleep(1)
            
        return False, "Exam results not found in any group", None

    except Exception as e:
        return False, f"Error !! : {str(e)}", None

def send_email(to_email, subject, body, gmail_user, gmail_pass):
    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = gmail_user
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Add body to email
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        # Create server object and send email
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(gmail_user, gmail_pass)
        server.send_message(msg)
        server.quit()
        
        print("E-mail sent successfully ...")
        return True
    except Exception as e:
        print(f"Error sending E-mail: {str(e)}")
        return False

# code for the script to work as a web service

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'OK')

def run_health_check():
    server = HTTPServer(('0.0.0.0', 8000), HealthCheckHandler)
    print("Health check server running on port 8000")
    server.serve_forever()

def main():
    # Start health check server in a separate thread
    health_check_thread = threading.Thread(target=run_health_check)
    health_check_thread.daemon = True
    health_check_thread.start()

    # Configuration
    STUDENT_ID = os.getenv("STD_SEAT_NUM") # student name or ID number
    FACULTY_ID = "2"  # Faculty of Law
    
    # Email configuration
    EMAIL_TO = os.getenv("to_email_addr")
    GMAIL_USER = os.getenv("from_email_addr")
    GMAIL_PASS = os.getenv("from_email_pass")
    
    # Check interval in seconds (2.5 hours)
    CHECK_INTERVAL = 9000
    
    print("Start checking Exam results ...")
    results_found = False
    
    while not results_found:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\nChecking results at {current_time}")
        
        results_found, message, group_name = check_exam_results(STUDENT_ID, FACULTY_ID)
        
        if results_found:
            print("\n" + "═"*50)
            print(message)
            print("═"*50 + "\n")
            
            
            # Send email notification with results
            email_subject = f"نتائج الامتحانات متاحة - {group_name}"
            email_body = f"""
            تم العثور على نتائج الامتحانات!
            المجموعة: {group_name}
            
            {message}
            
            """
            
            send_email(EMAIL_TO, email_subject, email_body, GMAIL_USER, GMAIL_PASS)
        else:
            print(f"Exam Checker says : {message}")
            print(f"Checking again at {CHECK_INTERVAL//60} minutes ...")
            time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main() 
