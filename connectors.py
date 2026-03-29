import os
import io
import json
import requests
import msal
import streamlit as st
from github import Github
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# --- API SCOPES ---
GOOGLE_SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
MS_SCOPES = ["Files.ReadWrite.All"]

# --- 1. MULTI-USER GOOGLE DRIVE AUTH (WEB FLOW) ---
def get_gdrive_service():
    """Handles multi-user login using Web App credentials from Secrets."""
    
    # 1. Check the 'Vault' (Streamlit Secrets)
    if "GOOGLE_CREDENTIALS_JSON" in st.secrets:
        # We load the text directly from the Cloud memory
        client_config = json.loads(st.secrets["GOOGLE_CREDENTIALS_JSON"])
    else:
        # 2. Local Fallback (Only for your PC)
        try:
            with open('GOOGLE_CREDENTIALS_JSON.json', 'r') as f:
                client_config = json.load(f)
        except FileNotFoundError:
            st.error("❌ Setup Error: No Secret found on Cloud, and no 'GOOGLE_CREDENTIALS_JSON.json' found locally.")
            st.stop()

    # 3. Proceed with the Multi-User Login
    if 'google_creds' not in st.session_state:
        redirect_uri = st.secrets.get("REDIRECT_URI", "http://localhost")
        
        flow = Flow.from_client_config(
            client_config,
            scopes=GOOGLE_SCOPES,
            redirect_uri=redirect_uri
        )

        auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
        st.info("👋 Please log in to Google Drive:")
        st.link_button("🔑 Login with Google", auth_url)

        if "code" in st.query_params:
            flow.fetch_token(code=st.query_params["code"])
            st.session_state.google_creds = flow.credentials
            st.rerun()
        else:
            st.stop()

    return build('drive', 'v3', credentials=st.session_state.google_creds)

def download_from_gdrive(service, file_id):
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return fh.getvalue()

# --- 2. MULTI-USER MICROSOFT AUTH (DEVICE FLOW) ---
def get_ms_token(ms_client_id):
    """Uses Device Code Flow for headless cloud environments."""
    if f"ms_token_{ms_client_id}" in st.session_state:
        return st.session_state[f"ms_token_{ms_client_id}"]

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
    
    # This blocks until the user completes login on their device
    result = app.acquire_token_by_device_flow(flow)
    
    if "access_token" in result:
        st.session_state[f"ms_token_{ms_client_id}"] = result
        return result
    return None

# --- 3. GITHUB CONNECTOR ---
def get_github_resumes(github_token, repo_name, folder_path=""):
    g = Github(github_token)
    try:
        repo = g.get_repo(repo_name)
        contents = repo.get_contents(folder_path)
        resumes = []
        if not isinstance(contents, list): contents = [contents]

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