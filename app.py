import streamlit as st
import connectors
import pandas as pd

# --- PAGE CONFIG ---
st.set_page_config(page_title="Multi-User Resume Sync", layout="wide")

# --- UI HEADER ---
st.title("📂 Multi-User Resume Sync Agent")
st.markdown("""
    This tool syncs resumes from **Google Drive** or **GitHub** to **OneDrive** based on the category (Java, Python, etc.) found in the logged-in user's account.
""")

# --- SIDEBAR: AUTH & SETTINGS ---
with st.sidebar:
    st.header("🔐 Authentication")
    
    # Check if user is logged into Google
    if 'google_creds' in st.session_state:
        st.success("✅ Connected to Google Drive")
        if st.button("🚪 Logout / Switch Account"):
            connectors.logout()
    else:
        # This will trigger the login button from connectors.py
        g_service = connectors.get_gdrive_service()

    st.divider()
    
    # Settings for Sync
    st.header("⚙️ Sync Settings")
    category = st.selectbox("Select Category to Sync", ["Java", "Python", "Data Science", "DevOps"])
    ms_client_id = st.text_input("Microsoft Client ID", value=st.secrets.get("MS_CLIENT_ID", ""))
    target_onedrive_path = st.text_input("OneDrive Target Folder", value=f"Resumes/{category}")

# --- MAIN LOGIC: SYNC PROCESS ---
if st.button(f"🚀 Sync {category} Resumes Now"):
    # 1. Initialize Google Service
    g_service = connectors.get_gdrive_service()
    
    with st.status(f"Scanning Google Drive for '{category}' folder...", expanded=True) as status:
        # 2. DYNAMIC FOLDER SEARCH
        # Instead of a hardcoded ID, we find the folder in THIS user's drive
        g_folder_id = connectors.find_gdrive_folder(g_service, category)
        
        if not g_folder_id:
            st.error(f"❌ Folder '{category}' not found in your Google Drive. Please create it and upload resumes.")
            st.stop()
        
        st.write(f"✅ Found '{category}' folder (ID: {g_folder_id})")
        
        # 3. Fetch Files from Google Drive
        results = g_service.files().list(
            q=f"'{g_folder_id}' in parents and trashed = false",
            fields="files(id, name)"
        ).execute()
        files = results.get('files', [])
        
        if not files:
            st.warning("⚠️ No resumes found in the Google Drive folder.")
            st.stop()

        # 4. Check OneDrive for existing files to avoid duplicates
        st.write("Checking OneDrive for duplicates...")
        existing_on_onedrive = connectors.get_onedrive_files(ms_client_id, target_onedrive_path)
        
        # 5. Sync Loop
        synced_count = 0
        for file in files:
            file_name = file['name']
            
            if file_name in existing_on_onedrive:
                st.write(f"⏩ Skipping {file_name} (Already in OneDrive)")
                continue
            
            st.write(f"⬇️ Downloading {file_name}...")
            file_content = connectors.download_from_gdrive(g_service, file['id'])
            
            st.write(f"⬆️ Uploading {file_name} to OneDrive...")
            status_code = connectors.upload_to_onedrive(
                file_content, 
                file_name, 
                ms_client_id, 
                target_onedrive_path
            )
            
            if status_code in [200, 201]:
                synced_count += 1
        
        status.update(label="✅ Sync Complete!", state="complete", expanded=False)

    st.success(f"Successfully synced {synced_count} new resumes to {target_onedrive_path}!")

# --- DISPLAY RECENT SYNC DATA ---
st.divider()
st.subheader("📊 Current Session Info")
col1, col2 = st.columns(2)
with col1:
    st.info(f"**Target Category:** {category}")
with col2:
    is_logged_in = "Yes" if 'google_creds' in st.session_state else "No"
    st.info(f"**Authenticated:** {is_logged_in}")