import os
import io
import requests
import msal
from github import Github
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# --- API SCOPES ---
GOOGLE_SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
MS_SCOPES = ["Files.ReadWrite.All"]

# --- GOOGLE DRIVE CONNECTORS ---

def get_gdrive_service():
    """Authenticates and returns the Google Drive API service."""
    creds = None
    # token_google.json stores the user's access and refresh tokens
    if os.path.exists('token_google.json'):
        creds = Credentials.from_authorized_user_file('token_google.json', GOOGLE_SCOPES)
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', GOOGLE_SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token_google.json', 'w') as token:
            token.write(creds.to_json())
            
    return build('drive', 'v3', credentials=creds)

def download_from_gdrive(service, file_id):
    """Downloads a file's content from Google Drive using its ID."""
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return fh.getvalue()


# --- GITHUB CONNECTORS ---

def get_github_resumes(github_token, repo_name, folder_path=""):
    """
    Fetches resumes from a specific GitHub repository folder.
    Returns a list of dicts with 'name' and 'content'.
    """
    g = Github(github_token)
    try:
        repo = g.get_repo(repo_name)
        contents = repo.get_contents(folder_path)
        resumes = []
        
        # If folder_path is empty, contents is a list of root items.
        # If folder_path has items, it iterates through them.
        for content in contents:
            if content.name.lower().endswith(('.pdf', '.docx')):
                resumes.append({
                    'name': content.name,
                    'content': content.decoded_content
                })
        return resumes
    except Exception as e:
        print(f"GitHub Error: {e}")
        return []


# --- MICROSOFT ONEDRIVE CONNECTORS ---

def get_onedrive_files(ms_client_id, folder_path):
    """
    Lists file names in a specific OneDrive subfolder to avoid duplicates.
    folder_path example: 'resumes/Java'
    """
    app = msal.PublicClientApplication(ms_client_id, authority="https://login.microsoftonline.com/common")
    accounts = app.get_accounts()
    
    result = None
    if accounts:
        result = app.acquire_token_silent(MS_SCOPES, account=accounts[0])
    
    if not result:
        result = app.acquire_token_interactive(scopes=MS_SCOPES)
        
    if "access_token" in result:
        headers = {'Authorization': f'Bearer {result["access_token"]}'}
        # Get children of the specific subfolder path
        url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{folder_path}:/children"
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            return [file['name'] for file in response.json().get('value', [])]
        else:
            return [] # Folder might not exist yet
    return []

def upload_to_onedrive(file_content, file_name, ms_client_id, folder_path):
    """
    Uploads binary content to a specific folder path in OneDrive.
    Microsoft Graph will auto-create the folder path if it doesn't exist.
    """
    app = msal.PublicClientApplication(ms_client_id, authority="https://login.microsoftonline.com/common")
    accounts = app.get_accounts()
    
    result = None
    if accounts:
        result = app.acquire_token_silent(MS_SCOPES, account=accounts[0])
    
    if not result:
        result = app.acquire_token_interactive(scopes=MS_SCOPES)
    
    if "access_token" in result:
        headers = {
            'Authorization': f'Bearer {result["access_token"]}',
            'Content-Type': 'application/octet-stream'
        }
        # Dynamic URL targeting the specific category folder
        url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{folder_path}/{file_name}:/content"
        
        response = requests.put(url, headers=headers, data=file_content)
        return response.status_code
    return None