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

# --- 1. MULTI-USER GOOGLE DRIVE AUTH (WEB FLOW) ---

def get_gdrive_service():
    if "GOOGLE_CREDENTIALS_JSON" not in st.secrets:
        st.error("❌ Setup Error: GOOGLE_CREDENTIALS_JSON not found in Streamlit Secrets.")
        st.stop()

    client_config = json.loads(st.secrets["GOOGLE_CREDENTIALS_JSON"])
    redirect_uri = st.secrets.get("REDIRECT_URI")

    # 1. SUCCESS: Already logged in
    if 'google_creds' in st.session_state:
        return build('drive', 'v3', credentials=st.session_state.google_creds)

    # 2. CREATE FLOW: Save it in session to keep the "Code Verifier" safe
    if 'auth_flow' not in st.session_state:
        st.session_state.auth_flow = Flow.from_client_config(
            client_config,
            scopes=GOOGLE_SCOPES,
            redirect_uri=redirect_uri
        )

    # 3. HANDLE REDIRECT: Google sent us back with a 'code'
    if "code" in st.query_params:
        code = st.query_params["code"]
        
        # SAFETY LOCK: Prevent Streamlit from running this twice
        if 'processing_code' not in st.session_state:
            st.session_state.processing_code = True
            try:
                # Exchange the code for the real credentials
                flow = st.session_state.auth_flow
                flow.fetch_token(code=code)
                
                # Save credentials and clean up
                st.session_state.google_creds = flow.credentials
                del st.session_state.auth_flow
                del st.session_state.processing_code
                
                # Clear the URL so the code is gone, then rerun
                st.query_params.clear()
                st.rerun()
                
            except Exception as e:
                # If it still fails, show exactly what URI is causing the mismatch
                st.error("❌ Google rejected the handshake. Let's fix this.")
                st.warning(f"**Error Details:** {e}")
                st.info(f"**Your App is sending this Redirect URI:** `{redirect_uri}`\n\n"
                        "Please go to Google Cloud Console and make sure the **Authorized redirect URIs** matches the above URL character-for-character.")
                
                # Provide a reset button
                if st.button("🔄 Clear Error and Try Again"):
                    st.query_params.clear()
                    del st.session_state.auth_flow
                    del st.session_state.processing_code
                    st.rerun()
                st.stop()
        else:
            # If processing_code is true, Streamlit is double-firing. Stop it here.
            st.stop()
    
    # 4. SHOW LOGIN BUTTON
    else:
        auth_url, _ = st.session_state.auth_flow.authorization_url(
            prompt='consent', 
            access_type='offline'
        )
        st.info("👋 Welcome! Please log in to your Google Drive:")
        st.link_button("🔑 Login with Google", auth_url)
        st.stop()

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

# --- 2. MULTI-USER MICROSOFT AUTH (DEVICE FLOW) ---
def get_ms_token(ms_client_id):
    session_key = f"ms_token_{ms_client_id}"
    if session_key in st.session_state:
        return st.session_state[session_key]

    app = msal.PublicClientApplication(ms_client_id, authority="https://login.microsoftonline.com/common")
    flow = app.initiate_device_flow(scopes=MS_SCOPES)
    
    if "user_code" not in flow:
        st.error("Microsoft Auth Error: Check your Client ID.")
        st.stop()

    st.warning("🔑 **Microsoft Login Required**")
    st.write(f"1. Go to: {flow['verification_uri']}")
    st.write(f"2. Enter this code: :red[**{flow['user_code']}**]")
    
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" in result:
        st.session_state[session_key] = result
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
                resumes.append({'name': content.name, 'content': content.decoded_content})
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
        headers = {'Authorization': f'Bearer {token_res["access_token"]}', 'Content-Type': 'application/octet-stream'}
        url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{folder_path}/{file_name}:/content"
        response = requests.put(url, headers=headers, data=file_content)
        return response.status_code
    return None

# --- 5. LOGOUT ---
def logout():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()