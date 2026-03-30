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

# --- THE MAGIC FIX: GLOBAL CACHE FOR OAUTH FLOW ---
# This dictionary survives across new tabs and page refreshes!
@st.cache_resource
def get_flow_cache():
    return {}

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

    params = st.query_params
    flow_cache = get_flow_cache()

    # 2. HANDLE REDIRECT: Google sent us back with a 'code' and 'state'
    if "code" in params and "state" in params:
        state = params["state"]
        
        # Retrieve the EXACT flow object from our global cache using the state
        if state in flow_cache:
            flow = flow_cache[state]
            try:
                # Exchange the code for the real credentials
                flow.fetch_token(code=params["code"])
                
                # Save credentials to this new tab's session state
                st.session_state.google_creds = flow.credentials
                
                # Clean up the cache memory
                del flow_cache[state]
                
                # Clear the URL so the code is gone, then rerun
                st.query_params.clear()
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ Handshake failed: {e}")
                st.query_params.clear()
                st.stop()
        else:
            # If the server rebooted while they were logging in
            st.error("❌ Session lost. Please close this tab and try clicking Login from the original tab again.")
            if st.button("Start Over"):
                st.query_params.clear()
                st.rerun()
            st.stop()
    
    # 3. SHOW LOGIN BUTTON
    else:
        # Create a brand new flow
        flow = Flow.from_client_config(
            client_config,
            scopes=GOOGLE_SCOPES,
            redirect_uri=redirect_uri
        )
        
        # Generate the auth URL and a unique 'state' parameter
        auth_url, state = flow.authorization_url(
            prompt='consent', 
            access_type='offline',
            include_granted_scopes='true'
        )
        
        # SAVE the flow in the global cache using the 'state' as the key
        flow_cache[state] = flow

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

# --- 3. GLOBAL GITHUB CONNECTOR ---
def get_global_github_resumes(github_token, keyword, max_results=10):
    """Searches ALL public GitHub repositories for resumes matching the keyword."""
    g = Github(github_token)
    resumes = []
    
    try:
        # Construct the global search query
        query = f"{keyword} resume extension:pdf"
        results = g.search_code(query=query)
        
        count = 0
        for file in results:
            if count >= max_results:
                break
                
            try:
                # Create a unique name to prevent overwriting files with the same name
                repo_owner = file.repository.owner.login
                safe_name = f"{repo_owner}_{file.name}"
                
                # Bypass the 1MB GitHub API limit by downloading raw URLs
                if file.download_url:
                    response = requests.get(file.download_url)
                    if response.status_code == 200:
                        file_content = response.content
                    else:
                        continue 
                else:
                    file_content = file.decoded_content
                
                resumes.append({'name': safe_name, 'content': file_content})
                count += 1
                
            except Exception as dl_err:
                continue # Skip files that cause errors and move to the next
                
        return resumes
        
    except Exception as e:
        st.error(f"❌ Global GitHub Search Error: {e}")
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