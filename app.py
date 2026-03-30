import streamlit as st
import connectors

# --- PAGE CONFIG ---
st.set_page_config(page_title="Multi-Source Resume Sync", layout="wide")

# Catch Google return code immediately
if "code" in st.query_params:
    connectors.get_gdrive_service()

st.title("🚀 Multi-Source Resume Sync Agent")

# --- SIDEBAR: CONNECTIONS DASHBOARD ---
with st.sidebar:
    st.header("🔗 Step 1: Connect Accounts")
    
    # 1. Google Auth
    g_service, g_auth_url = connectors.get_gdrive_service()
    if g_service:
        st.success("✅ Google Drive Connected")
        if st.button("🚪 Logout All Accounts"):
            connectors.logout()
    elif g_auth_url:
        st.warning("⚠️ Google Drive Disconnected")
        st.link_button("🔑 Login to Google Drive", g_auth_url)

    st.divider()
    
    # 2. Microsoft Auth
    ms_client_id = st.secrets.get("MS_CLIENT_ID")
    if not ms_client_id:
        st.error("❌ MS_CLIENT_ID missing from secrets.")
        st.stop()
        
    ms_connected = connectors.is_ms_connected(ms_client_id)
    if ms_connected:
        st.success("✅ OneDrive Connected")
    else:
        st.warning("⚠️ OneDrive Disconnected")
        if st.button("☁️ Connect OneDrive"):
            connectors.trigger_ms_login(ms_client_id, st.sidebar)
            
    # 3. GitHub Token (Hidden from user, loaded securely)
    gh_token = st.secrets.get("GITHUB_TOKEN")
    if not gh_token:
        st.error("❌ GITHUB_TOKEN missing from secrets.")
        st.stop()


# --- MAIN UI: TABS ---
tab1, tab2 = st.tabs(["📂 Sync from Google Drive", "🌍 Global GitHub Search"])

# ==========================================
# TAB 1: GOOGLE DRIVE SYNC (WITH GITHUB FALLBACK)
# ==========================================
with tab1:
    st.header("Google Drive to OneDrive (Smart Sync)")
    st.write("Sync a specific folder from Drive. If the folder is empty or missing, it automatically searches GitHub!")
    
    col1, col2 = st.columns(2)
    with col1:
        g_category = st.selectbox("Category Folder", ["Java", "Python", "Data Science", "DevOps", "SAP"], key="g_cat")
    with col2:
        g_target_path = st.text_input("OneDrive Target Folder", value=f"Resumes/{g_category}", key="g_path")

    if st.button(f"🚀 Smart Sync '{g_category}'"):
        if not g_service:
            st.error("❌ Please connect Google Drive in the sidebar first.")
        elif not ms_connected:
            st.error("❌ Please connect Microsoft OneDrive in the sidebar first.")
        else:
            with st.status(f"Scanning Google Drive for '{g_category}'...", expanded=True) as status:
                st.write("Looking for folder...")
                g_folder_id = connectors.find_gdrive_folder(g_service, g_category)
                
                # Try to fetch files from Google Drive
                files = []
                if g_folder_id:
                    results = g_service.files().list(q=f"'{g_folder_id}' in parents and trashed = false", fields="files(id, name)").execute()
                    files = results.get('files', [])
                
                st.write("Checking OneDrive for duplicates...")
                existing_on_onedrive = connectors.get_onedrive_files(ms_client_id, g_target_path)
                synced_count = 0

                # SCENARIO A: Files found in Google Drive
                if files:
                    st.write(f"✅ Found {len(files)} files in Google Drive.")
                    for file in files:
                        file_name = file['name']
                        if file_name in existing_on_onedrive:
                            st.write(f"⏩ Skipping **{file_name}**")
                            continue
                        
                        st.write(f"⬆️ Moving **{file_name}**...")
                        file_content = connectors.download_from_gdrive(g_service, file['id'])
                        connectors.upload_to_onedrive(file_content, file_name, ms_client_id, g_target_path)
                        synced_count += 1
                    
                    status.update(label=f"✅ Synced {synced_count} files from Drive!", state="complete", expanded=False)
                    st.toast(f"Successfully synced {synced_count} files from Drive!", icon="🚀")

                # SCENARIO B: No files found! Fallback to GitHub
                else:
                    st.warning(f"⚠️ No resumes found in Google Drive for '{g_category}'. Activating GitHub Fallback...")
                    st.write(f"🔍 Pinging GitHub API for '{g_category}' resumes (Limit: 5)...")
                    
                    github_files = connectors.get_global_github_resumes(gh_token, g_category, max_results=5)
                    
                    if not github_files:
                        st.error(f"❌ Could not find '{g_category}' resumes in Drive OR GitHub.")
                        status.update(label="❌ Sync Failed: No files found anywhere.", state="error", expanded=False)
                    else:
                        st.write(f"✅ Downloaded {len(github_files)} fallback resumes from GitHub.")
                        for file in github_files:
                            file_name = file['name']
                            if file_name in existing_on_onedrive:
                                st.write(f"⏩ Skipping **{file_name}**")
                                continue
                                
                            st.write(f"⬆️ Uploading **{file_name}**...")
                            connectors.upload_to_onedrive(file['content'], file_name, ms_client_id, g_target_path)
                            synced_count += 1
                            
                        status.update(label=f"✅ Fallback successful! Synced {synced_count} global resumes.", state="complete", expanded=False)
                        st.toast(f"Fallback complete! Synced {synced_count} files from GitHub.", icon="🦸‍♂️")


# ==========================================
# TAB 2: GLOBAL GITHUB SEARCH (MANUAL)
# ==========================================
with tab2:
    st.header("Global GitHub to OneDrive")
    st.write("Manually scour the open-source GitHub community for specific resumes.")
    
    col3, col4 = st.columns(2)
    with col3:
        gh_category = st.selectbox("Search Keyword", ["Java", "Python", "React", "Data Science", "SAP"], key="gh_cat")
        max_downloads = st.slider("Max Resumes", 1, 20, 5)
    with col4:
        gh_target_path = st.text_input("OneDrive Target Folder", value=f"Resumes/Global_{gh_category}", key="gh_path_2")

    if st.button(f"🌍 Scrape World for '{gh_category}'"):
        if not ms_connected:
            st.error("❌ Please connect Microsoft OneDrive in the sidebar first.")
        else:
            with st.status(f"Searching GitHub globally for '{gh_category}'...", expanded=True) as status:
                st.write("🔍 Pinging GitHub API...")
                
                # Fetch from GitHub
                github_files = connectors.get_global_github_resumes(gh_token, gh_category, max_downloads)
                
                if not github_files:
                    st.warning("⚠️ No public resumes found or GitHub API limit reached.")
                else:
                    st.write(f"✅ Downloaded {len(github_files)} resumes. Checking OneDrive...")
                    existing_on_onedrive = connectors.get_onedrive_files(ms_client_id, gh_target_path)
                    
                    synced_count = 0
                    for file in github_files:
                        file_name = file['name']
                        if file_name in existing_on_onedrive:
                            st.write(f"⏩ Skipping **{file_name}**")
                            continue
                            
                        st.write(f"⬆️ Uploading **{file_name}**...")
                        connectors.upload_to_onedrive(file['content'], file_name, ms_client_id, gh_target_path)
                        synced_count += 1
                        
                    status.update(label=f"✅ Synced {synced_count} global resumes!", state="complete", expanded=False)
                    st.toast(f"Successfully scraped {synced_count} files!", icon="🎉")