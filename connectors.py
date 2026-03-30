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

GOOGLE_SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
MS_SCOPES = ["Files.ReadWrite.All"]

@st.cache_resource
def get_flow_cache():
    return {}

# --- 1. NON-BLOCKING GOOGLE AUTH ---
def get_gdrive_service():
    """Returns (service, None) if logged in, or (None, auth_url) if not."""
    if "GOOGLE_CREDENTIALS_JSON" not in st.secrets:
        st.error("❌ Setup Error: GOOGLE_CREDENTIALS_JSON not found in Secrets.")
        return None, None

    client_config = json.loads(st.secrets["GOOGLE_CREDENTIALS_JSON"])
    redirect_uri = st.secrets.get("REDIRECT_URI")

    # 1. SUCCESS: Already logged in
    if 'google_creds' in st.session_state:
        service = build('drive', 'v3', credentials=st.session_state.google_creds)
        return service, None

    params = st.query_params
    flow_cache = get_flow_cache()

    # 2. HANDLE REDIRECT
    if "code" in params and "state" in params:
        state = params["state"]
        if state in flow_cache:
            flow = flow_cache[state]
            try:
                flow.fetch_token(code=params["code"])
                st.session_state.google_creds = flow.credentials
                del flow_cache[state]
                st.query_params.clear()
                st.rerun()
            except Exception as e:
                st.error(f"❌ Google Handshake failed: {e}")
                st.query_params.clear()
        return None, None
    
    # 3. GENERATE LOGIN URL (Do not stop the app!)
    else:
        flow = Flow.from_client_config(client_config, scopes=GOOGLE_SCOPES, redirect_uri=redirect_uri)
        auth_url, state = flow.authorization_url(prompt='consent', access_type='offline', include_granted_scopes='true')
        flow_cache[state] = flow
        return None, auth_url

def find_gdrive_folder(service, folder_name):
    query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    items = results.get('files', [])
    return items[0]['id'] if items else None

def download_from_gdrive(service, file_id):
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return fh.getvalue()

# --- 2. NON-BLOCKING MICROSOFT AUTH ---
def is_ms_connected(ms_client_id):
    """Checks if the Microsoft token exists in the session."""
    return f"ms_token_{ms_client_id}" in st.session_state

def trigger_ms_login(ms_client_id, container=st):
    """Triggers the Device Code flow in a specific UI container."""
    app = msal.PublicClientApplication(ms_client_id, authority="https://login.microsoftonline.com/common")
    flow = app.initiate_device_flow(scopes=MS_SCOPES)
    
    if "user_code" not in flow:
        container.error("❌ Microsoft Auth Error: Check your Client ID.")
        return

    container.warning("🔑 **Microsoft Login Required**")
    container.markdown(f"1. Go to: **[Microsoft Device Login]({flow['verification_uri']})**")
    container.markdown(f"2. Enter code: **`{flow['user_code']}`**")
    container.info("⏳ *Waiting for you to complete login on Microsoft's website...*")
    
    # Blocks here safely until the user completes the login
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" in result:
        st.session_state[f"ms_token_{ms_client_id}"] = result
        st.rerun()

# --- 3. GLOBAL GITHUB CONNECTOR ---
def get_global_github_resumes(github_token, keyword, max_results=10):
    g = Github(github_token)
    resumes = []
    try:
        query = f"{keyword} resume extension:pdf"
        results = g.search_code(query=query)
        count = 0
        for file in results:
            if count >= max_results: break
            try:
                safe_name = f"{file.repository.owner.login}_{file.name}"
                if file.download_url:
                    response = requests.get(file.download_url)
                    if response.status_code == 200: file_content = response.content
                    else: continue 
                else:
                    file_content = file.decoded_content
                resumes.append({'name': safe_name, 'content': file_content})
                count += 1
            except Exception:
                continue 
        return resumes
    except Exception as e:
        st.error(f"❌ Global GitHub Search Error: {e}")
        return []

# --- 4. ONEDRIVE CONNECTORS ---
def get_onedrive_files(ms_client_id, folder_path):
    if not is_ms_connected(ms_client_id): return []
    token = st.session_state[f"ms_token_{ms_client_id}"]["access_token"]
    headers = {'Authorization': f'Bearer {token}'}
    url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{folder_path}:/children"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return [file['name'] for file in response.json().get('value', [])]
    return []

def upload_to_onedrive(file_content, file_name, ms_client_id, folder_path):
    if not is_ms_connected(ms_client_id): return None
    token = st.session_state[f"ms_token_{ms_client_id}"]["access_token"]
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/octet-stream'}
    url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{folder_path}/{file_name}:/content"
    response = requests.put(url, headers=headers, data=file_content)
    return response.status_code

# --- 5. LOGOUT ---
def logout():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()