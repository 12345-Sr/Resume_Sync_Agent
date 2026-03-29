import os
import io
import requests
import msal
import json
import streamlit as st
from github import Github
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# --- API SCOPES ---
GOOGLE_SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
MS_SCOPES = ["Files.ReadWrite.All"]

# --- HELPER: GOOGLE AUTH ---
def get_gdrive_service():
    creds = None
    # 1. Check for token_google.json (Session Token)
    if os.path.exists('token_google.json'):
        creds = Credentials.from_authorized_user_file('token_google.json', GOOGLE_SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # 2. If file is missing, try reading from Streamlit Secrets
            if "GOOGLE_CREDENTIALS_JSON" in st.secrets:
                creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS_JSON"])
                flow = InstalledAppFlow.from_client_config(creds_dict, GOOGLE_SCOPES)
                
                # IMPORTANT: On Cloud, this will still trigger the 'No Browser' error.
                # The best way is to generate 'token_google.json' locally 
                # and paste ITS content into Secrets too.
                creds = flow.run_local_server(port=0) 
            else:
                st.error("Google Credentials not found in files or Secrets!")
                st.stop()
                
    return build('drive', 'v3', credentials=creds)

def download_from_gdrive(service, file_id):
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return fh.getvalue()

# --- HELPER: MICROSOFT AUTH (DEVICE FLOW) ---
def get_ms_token(ms_client_id):
    """Uses Device Code Flow for headless environments (Cloud/Codespaces)."""
    app = msal.PublicClientApplication(
        ms_client_id, 
        authority="https://login.microsoftonline.com/common"
    )
    
    accounts = app.get_accounts()
    result = None

    if accounts:
        result = app.acquire_token_silent(MS_SCOPES, account=accounts[0])

    if not result:
        # START DEVICE FLOW
        flow = app.initiate_device_flow(scopes=MS_SCOPES)
        if "user_code" not in flow:
            st.error("Failed to create Microsoft Device Flow. Check your Client ID.")
            st.stop()

        # Display the code to the user in the Streamlit UI
        st.warning(f"🔑 **Microsoft Login Required**")
        st.write(f"1. Go to: {flow['verification_uri']}")
        st.write(f"2. Enter this code: **{flow['user_code']}**")
        
        # This blocks until the user enters the code on their phone/PC
        result = app.acquire_token_by_device_flow(flow)
    
    return result

# --- GITHUB CONNECTORS ---
def get_github_resumes(github_token, repo_name, folder_path=""):
    g = Github(github_token)
    try:
        repo = g.get_repo(repo_name)
        contents = repo.get_contents(folder_path)
        resumes = []
        
        # Wrap in list if it's a single file, though usually it's a list for folders
        if not isinstance(contents, list):
            contents = [contents]

        for content in contents:
            if content.name.lower().endswith(('.pdf', '.docx')):
                resumes.append({
                    'name': content.name,
                    'content': content.decoded_content
                })
        return resumes
    except Exception as e:
        st.error(f"GitHub Error: {e}")
        return []

# --- MICROSOFT ONEDRIVE CONNECTORS ---
def get_onedrive_files(ms_client_id, folder_path):
    token_res = get_ms_token(ms_client_id)
    
    if token_res and "access_token" in token_res:
        headers = {'Authorization': f'Bearer {token_res["access_token"]}'}
        url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{folder_path}:/children"
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            return [file['name'] for file in response.json().get('value', [])]
    return []

def upload_to_onedrive(file_content, file_name, ms_client_id, folder_path):
    token_res = get_ms_token(ms_client_id)
    
    if token_res and "access_token" in token_res:
        headers = {
            'Authorization': f'Bearer {token_res["access_token"]}',
            'Content-Type': 'application/octet-stream'
        }
        url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{folder_path}/{file_name}:/content"
        response = requests.put(url, headers=headers, data=file_content)
        return response.status_code
    return None