import streamlit as st
import main
from connectors import (
    get_gdrive_service, download_from_gdrive,
    upload_to_onedrive, get_github_resumes, get_onedrive_files
)

st.set_page_config(page_title="Resume Sync AI: Categorized Sync", page_icon="🎯")
st.title("🎯 Categorized Resume Agent")

# --- CATEGORY SELECTION ---
category = st.selectbox("Select Resume Category to Sync:", ["java", "python", "PHP", ".NET"])
target_path = f"resumes/{category}" # This creates 'resumes/Java' in OneDrive

# --- CONFIGURATION (Pre-filled from main.py) ---
with st.sidebar:
    st.header("Settings")
    ms_id = st.text_input("Microsoft Client ID", value=main.MICROSOFT_CLIENT_ID)
    g_parent_id = st.text_input("Main Google Folder ID", value=main.G_DRIVE_FOLDER_ID)
    gh_repo = st.text_input("GitHub Repo", value=main.GITHUB_REPO)
    gh_token = st.text_input("GitHub Token", value=main.GITHUB_TOKEN, type="password")

if st.button(f"🚀 Sync all {category} Resumes"):
    with st.status(f"Processing {category} folder...", expanded=True) as status:
        
        # 1. Get existing files in the SPECIFIC OneDrive subfolder
        st.write(f"🔍 Checking OneDrive: `{target_path}`")
        existing = get_onedrive_files(ms_id, folder_path=target_path)

        # 2. Google Drive Logic (Search for subfolder named 'category')
        st.write(f"📥 Searching Google Drive for `{category}` subfolder...")
        g_service = get_gdrive_service()
        # Find the subfolder ID inside the parent
        subfolder_query = f"name = '{category}' and '{g_parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder'"
        subfolder_result = g_service.files().list(q=subfolder_query).execute().get('files', [])
        
        if subfolder_result:
            sub_id = subfolder_result[0]['id']
            files = g_service.files().list(q=f"'{sub_id}' in parents").execute().get('files', [])
            for f in files:
                if f['name'] not in existing:
                    content = download_from_gdrive(g_service, f['id'])
                    # Upload to the same subfolder in OneDrive
                    upload_to_onedrive(content, f['name'], ms_id, folder_path=target_path)
                    st.success(f"Google: {f['name']} -> OneDrive/{category}")
        else:
            st.warning(f"No '{category}' folder found in Google Drive.")

        # 3. GitHub Logic (Targeting 'category/' folder)
        try:
            st.write(f"📡 Checking GitHub: `{gh_repo}` for `{category}` resumes...")
            
            # We pass the category to our search function
            gh_files = get_github_resumes(gh_token, gh_repo, folder_path=category)
            
            if not gh_files:
                st.info(f"Empty or missing folder: `{category}` on GitHub. Skipping...")
            else:
                for f in gh_files:
                    if f['name'] not in existing:
                        upload_to_onedrive(f['content'], f['name'], ms_id, folder_path=target_path)
                        st.success(f"GitHub: {f['name']} -> OneDrive/{category}")
                    else:
                        st.info(f"⏭️ {f['name']} already in OneDrive.")
                        
        except Exception as e:
            st.error(f"GitHub Sync Error: {e}")