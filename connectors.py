import os
import io
import json
import requests
import msal
import streamlit as st
from github import Github
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# --- API SCOPES ---
# These define what the app is allowed to do. 
# 'readonly' for Google Drive is safer for a resume agent.
GOOGLE_SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
MS_SCOPES = ["Files.ReadWrite.All"]

# --- 1. MULTI-USER GOOGLE DRIVE AUTHENTICATION ---

def get_gdrive_service():
    """
    Handles login and prevents 'Missing code verifier' 
    by persisting the Flow object in session_state.
    """
    if "GOOGLE_CREDENTIALS_JSON" not in st.secrets:
        st.error("Missing GOOGLE_CREDENTIALS_JSON in Secrets.")
        st.stop()

    client_config = json.loads(st.secrets["GOOGLE_CREDENTIALS_JSON"])
    redirect_uri = st.secrets.get("REDIRECT_URI")

    # 1. If already authenticated for this session, return the service
    if 'google_creds' in st.session_state:
        return build('drive', 'v3', credentials=st.session_state.google_creds)

    # 2. THE FIX: Store the Flow object in session_state
    # This keeps the 'code_verifier' alive across the page refresh
    if 'auth_flow' not in st.session_state:
        st.session_state.auth_flow = Flow.from_client_config(
            client_config,
            scopes=GOOGLE_SCOPES,
            redirect_uri=redirect_uri
        )

    # 3. Check if the URL contains the 'code' from Google
    if "code" in st.query_params:
        try:
            # Use the SAVED flow object that has the ORIGINAL verifier
            st.session_state.auth_flow.fetch_token(code=st.query_params["code"])
            st.session_state.google_creds = st.session_state.auth_flow.credentials
            
            # Cleanup: remove the flow and clear URL params
            del st.session_state.auth_flow
            st.query_params.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Login failed: {e}")
            # Reset flow so the user can try again
            if 'auth_flow' in st.session_state:
                del st.session_state.auth_flow
            st.stop()
    
    # 4. Show Login Button
    else:
        auth_url, _ = st.session_state.auth_flow.authorization_url(
            prompt='consent', 
            access_type='offline'
        )
        st.info("👋 Welcome! Please log in to your Google Drive:")
        st.link_button("🔑 Login with Google", auth_url)
        st.stop()

def find_gdrive_folder(service, folder_name):
    """
    Searches the current logged-in user's Drive for a folder by name.
    Useful for finding 'Java', 'Python', or 'Resumes' folders.
    """
    query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    items = results.get('files', [])
    return items[0]['id'] if items else None

def download_from_gdrive(service, file_id):
    """Downloads a file from Google Drive as binary data."""
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return fh.getvalue()


# --- 2. MULTI-USER MICROSOFT AUTHENTICATION (DEVICE FLOW) ---

def get_ms_token(ms_client_id):
    """Uses Device Code Flow - each user authenticates their own OneDrive."""
    session_key = f"ms_token_{ms_client_id}"
    if session_key in st.session_state:
        return st.session_state[session_key]

    app = msal.PublicClientApplication(
        ms_client_id, 
        authority="https://login.microsoftonline.com/common"
    )
    
    flow = app.initiate_device_flow(scopes=MS_SCOPES)
    if "user_code" not in flow:
        st.error("Microsoft Auth Error: Check your Client ID.")
        st.stop()

    st.warning("🔑 **Microsoft Login Required**")
    st.write(f"1. Go to: {flow['verification_uri']}")
    st.write(f"2. Enter this code: :red[**{flow['user_code']}**]")
    
    # This blocks until the user enters the code on their other device
    result = app.acquire_token_by_device_flow(flow)
    
    if "access_token" in result:
        st.session_state[session_key] = result
        return result
    return None


# --- 3. GITHUB CONNECTOR ---

def get_github_resumes(github_token, repo_name, folder_path=""):
    """Fetches PDF/DOCX resumes from a specific GitHub repo folder."""
    g = Github(github_token)
    try:
        repo = g.get_repo(repo_name)
        contents = repo.get_contents(folder_path)
        resumes = []
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


# --- 4. ONEDRIVE CONNECTORS ---

def get_onedrive_files(ms_client_id, folder_path):
    """Lists files already in the target OneDrive folder to prevent duplicates."""
    token_res = get_ms_token(ms_client_id)
    if token_res and "access_token" in token_res:
        headers = {'Authorization': f'Bearer {token_res["access_token"]}'}
        url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{folder_path}:/children"
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return [file['name'] for file in response.json().get('value', [])]
    return []

def upload_to_onedrive(file_content, file_name, ms_client_id, folder_path):
    """Uploads binary content to a specific folder in OneDrive."""
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


# --- 5. SESSION CLEANUP (LOGOUT) ---

def logout():
    """Clears the session so a different user can log in."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()