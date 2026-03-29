import streamlit as st
import connectors  # Ensure connectors.py does NOT have 'import main' at the top

# --- SECURE CONFIGURATION LOADING ---
# We use a try/except block so the app doesn't crash if main.py is missing
ms_id_def = ""
g_folder_def = ""
gh_token_def = ""
gh_repo_def = ""

if "MICROSOFT_CLIENT_ID" in st.secrets:
    # 1. Check Streamlit Cloud Secrets first
    ms_id_def = st.secrets["MICROSOFT_CLIENT_ID"]
    g_folder_def = st.secrets["G_DRIVE_FOLDER_ID"]
    gh_token_def = st.secrets["GITHUB_TOKEN"]
    gh_repo_def = st.secrets["GITHUB_REPO"]
else:
    # 2. If not in cloud, try local main.py
    try:
        import main
        ms_id_def = main.MICROSOFT_CLIENT_ID
        g_folder_def = main.G_DRIVE_FOLDER_ID
        gh_token_def = main.GITHUB_TOKEN
        gh_repo_def = main.GITHUB_REPO
    except (ImportError, ModuleNotFoundError):
        # 3. If both fail, we just leave defaults as empty strings
        pass

st.set_page_config(page_title="Resume Sync AI", page_icon="🎯")
st.title("🎯 Categorized Resume Agent")

# --- UI SIDEBAR ---
# --- CONFIGURATION UI (Pre-filled from Secrets/Main) ---
with st.sidebar:
    st.header("Settings")
    # Added unique keys to distinguish these elements
    ms_id = st.text_input(
        "Microsoft Client ID", 
        value=ms_id_def, 
        key="ms_client_id_sidebar"
    )
    g_parent_id = st.text_input(
        "Main Google Folder ID", 
        value=g_folder_def, 
        key="g_folder_id_sidebar"
    )
    gh_repo = st.text_input(
        "GitHub Repo", 
        value=gh_repo_def, 
        key="gh_repo_sidebar"
    )
    gh_token = st.text_input(
        "GitHub Token", 
        value=gh_token_def, 
        type="password", 
        key="gh_token_sidebar"
    )
category = st.selectbox("Select Category:", ["java", "python", "PHP", ".NET"])
target_path = f"resumes/{category}" 

if st.button(f"🚀 Sync {category} Resumes"):
    if not ms_id or not g_parent_id or not gh_token:
        st.error("Missing configuration! Please fill the sidebar or set Streamlit Secrets.")
    else:
        # Your sync logic here...
        st.write(f"Syncing {category}...")

# --- CONFIGURATION UI (Pre-filled from Secrets/Main) ---
with st.sidebar:
    st.header("Settings")
    ms_id = st.text_input("Microsoft Client ID", value=ms_id_def)
    g_parent_id = st.text_input("Main Google Folder ID", value=g_folder_def)
    gh_repo = st.text_input("GitHub Repo", value=gh_repo_def)
    gh_token = st.text_input("GitHub Token", value=gh_token_def, type="password")

# --- SYNC LOGIC ---
if st.button(f"🚀 Sync all {category} Resumes"):
    if not ms_id or not g_parent_id or not gh_token:
        st.error("Please ensure all IDs are filled in the sidebar.")
        st.stop()

    with st.status(f"Processing {category} folder...", expanded=True) as status:
        
        # 1. Get existing files in the SPECIFIC OneDrive subfolder
        st.write(f"🔍 Checking OneDrive: `{target_path}`")
        try:
            # We use the connectors. prefix because we imported the whole module
            existing = connectors.get_onedrive_files(ms_id, folder_path=target_path)
        except Exception as e:
            st.error(f"OneDrive Connection Error: {e}")
            existing = []

        # 2. Google Drive Logic
        st.write(f"📥 Searching Google Drive for `{category}` subfolder...")
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
            st.write(f"📡 Checking GitHub: `{gh_repo}` for `{category}` resumes...")
            gh_files = connectors.get_github_resumes(gh_token, gh_repo, folder_path=category)
            
            if not gh_files:
                st.info(f"Empty or missing folder: `{category}` on GitHub.")
            else:
                for f in gh_files:
                    if f['name'] not in existing:
                        connectors.upload_to_onedrive(f['content'], f['name'], ms_id, folder_path=target_path)
                        st.success(f"GitHub: {f['name']} -> OneDrive/{category}")
                    else:
                        st.info(f"⏭️ GitHub: {f['name']} already in OneDrive.")
                        
        except Exception as e:
            st.error(f"GitHub Sync Error: {e}")

        status.update(label=f"{category} Sync Complete!", state="complete")