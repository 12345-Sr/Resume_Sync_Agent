import streamlit as st
import connectors  # Ensure connectors.py does NOT have 'import main' at the top

# --- SECURE CONFIGURATION LOADING ---
ms_id_def = ""
g_folder_def = ""
gh_token_def = ""
gh_repo_def = ""

if "MICROSOFT_CLIENT_ID" in st.secrets:
    ms_id_def = st.secrets["MICROSOFT_CLIENT_ID"]
    g_folder_def = st.secrets["G_DRIVE_FOLDER_ID"]
    gh_token_def = st.secrets["GITHUB_TOKEN"]
    gh_repo_def = st.secrets["GITHUB_REPO"]
else:
    try:
        import main
        ms_id_def = main.MICROSOFT_CLIENT_ID
        g_folder_def = main.G_DRIVE_FOLDER_ID
        gh_token_def = main.GITHUB_TOKEN
        gh_repo_def = main.GITHUB_REPO
    except (ImportError, ModuleNotFoundError):
        pass

st.set_page_config(page_title="Resume Sync AI", page_icon="🎯")
st.title("🎯 Categorized Resume Agent")

# --- CONFIGURATION UI (ONLY ONE SIDEBAR BLOCK) ---
with st.sidebar:
    st.header("Settings")
    ms_id = st.text_input("Microsoft Client ID", value=ms_id_def, key="ms_id_input")
    g_parent_id = st.text_input("Main Google Folder ID", value=g_folder_def, key="g_drive_input")
    gh_repo = st.text_input("GitHub Repo", value=gh_repo_def, key="gh_repo_input")
    gh_token = st.text_input("GitHub Token", value=gh_token_def, type="password", key="gh_token_input")

# --- CATEGORY SELECTION ---
category = st.selectbox("Select Category:", ["java", "python", "PHP", ".NET"])
target_path = f"resumes/{category}" 

# --- SYNC LOGIC (ONLY ONE BUTTON BLOCK) ---
if st.button(f"🚀 Sync all {category} Resumes"):
    if not ms_id or not g_parent_id or not gh_token:
        st.error("Please ensure all IDs are filled in the sidebar.")
        st.stop()

    with st.status(f"Processing {category} folder...", expanded=True) as status:
        
        # 1. Get existing files
        st.write(f"🔍 Checking OneDrive: `{target_path}`")
        try:
            existing = connectors.get_onedrive_files(ms_id, folder_path=target_path)
        except Exception as e:
            st.error(f"OneDrive Error: {e}")
            existing = []

        # 2. Google Drive Logic
        st.write(f"📥 Searching Google Drive for `{category}`...")
        try:
            g_service = connectors.get_gdrive_service()
            subfolder_query = f"name = '{category}' and '{g_parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder'"
            subfolder_result = g_service.files().list(q=subfolder_query).execute().get('files', [])
            
            if subfolder_result:
                sub_id = subfolder_result[0]['id']
                files = g_service.files().list(q=f"'{sub_id}' in parents").execute().get('files', [])
                for f in files:
                    if f['name'] not in existing:
                        content = connectors.download_from_gdrive(g_service, f['id'])
                        connectors.upload_to_onedrive(content, f['name'], ms_id, folder_path=target_path)
                        st.success(f"Google: {f['name']} -> OneDrive/{category}")
                    else:
                        st.info(f"⏭️ Google: {f['name']} already in OneDrive.")
            else:
                st.warning(f"No '{category}' folder found in Google Drive.")
        except Exception as e:
            st.error(f"Google Drive Error: {e}")

        # 3. GitHub Logic
        try:
            st.write(f"📡 Checking GitHub: `{gh_repo}`...")
            gh_files = connectors.get_github_resumes(gh_token, gh_repo, folder_path=category)
            
            if not gh_files:
                st.info(f"Empty or missing folder on GitHub.")
            else:
                for f in gh_files:
                    if f['name'] not in existing:
                        connectors.upload_to_onedrive(f['content'], f['name'], ms_id, folder_path=target_path)
                        st.success(f"GitHub: {f['name']} -> OneDrive/{category}")
                    else:
                        st.info(f"⏭️ GitHub: {f['name']} already in OneDrive.")
        except Exception as e:
            st.error(f"GitHub Error: {e}")

        status.update(label=f"{category} Sync Complete!", state="complete")