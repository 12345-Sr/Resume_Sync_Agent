import streamlit as st
import connectors

# --- PAGE CONFIG ---
st.set_page_config(page_title="Multi-Source Resume Sync", layout="wide")

# 1. ALWAYS PROCESS GOOGLE REDIRECT FIRST
# This catches the 'code' when you return from Google's login page
if "code" in st.query_params:
    connectors.get_gdrive_service()

# --- UI HEADER ---
st.title("🚀 Multi-Source Resume Sync Agent")
st.markdown("""
    Sync resumes seamlessly from your **Google Drive** or search the **Global GitHub Open Source** community, 
    and push them directly to your **Microsoft OneDrive**.
""")

# --- SIDEBAR: CONNECTIONS DASHBOARD ---
with st.sidebar:
    st.header("🔗 Step 1: Connect Accounts")
    
    # --- GOOGLE AUTH CHECK ---
    # Unpack the tuple to prevent the AttributeError!
    g_service, g_auth_url = connectors.get_gdrive_service()
    
    if g_service:
        st.success("✅ Google Drive Connected")
        if st.button("🚪 Logout All Accounts"):
            connectors.logout()
    elif g_auth_url:
        st.warning("⚠️ Google Drive Disconnected")
        st.link_button("🔑 Login to Google Drive", g_auth_url)

    st.divider()
    
    # --- MICROSOFT AUTH CHECK ---
    ms_client_id = st.secrets.get("MS_CLIENT_ID")
    if not ms_client_id:
        st.error("❌ Developer Error: MS_CLIENT_ID missing from secrets.")
        st.stop()
        
    ms_connected = connectors.is_ms_connected(ms_client_id)
    
    if ms_connected:
        st.success("✅ OneDrive Connected")
    else:
        st.warning("⚠️ OneDrive Disconnected")
        if st.button("☁️ Connect OneDrive"):
            # Triggers the Device Code flow seamlessly in the sidebar
            connectors.trigger_ms_login(ms_client_id, st.sidebar)


# --- MAIN UI: TABS ---
tab1, tab2 = st.tabs(["📂 Sync from Google Drive", "🌍 Global GitHub Search"])


# ==========================================
# TAB 1: GOOGLE DRIVE SYNC
# ==========================================
with tab1:
    st.header("Google Drive to OneDrive")
    st.write("Sync a specific folder from your personal Google Drive.")
    
    # Settings
    col1, col2 = st.columns(2)
    with col1:
        # Added 'SAP' to match your latest code
        g_category = st.selectbox("Select Category Folder", ["Java", "Python", "Data Science", "DevOps", "SAP"], key="g_cat")
    with col2:
        g_target_path = st.text_input("OneDrive Target Folder", value=f"Resumes/{g_category}", key="g_path")

    # Action Button
    if st.button(f"🚀 Sync '{g_category}' from Google Drive"):
        
        # PRE-FLIGHT CHECKS
        if not g_service:
            st.error("❌ Please connect Google Drive in the sidebar first.")
            st.stop()
        if not ms_connected:
            st.error("❌ Please connect Microsoft OneDrive in the sidebar first.")
            st.stop()
            
        with st.status(f"Scanning Google Drive for '{g_category}'...", expanded=True) as status:
            # 1. Find Folder
            g_folder_id = connectors.find_gdrive_folder(g_service, g_category)
            if not g_folder_id:
                st.error(f"❌ Folder '{g_category}' not found in your Google Drive.")
                st.stop()
            st.write(f"✅ Found '{g_category}' folder.")
            
            # 2. Fetch Files
            results = g_service.files().list(
                q=f"'{g_folder_id}' in parents and trashed = false", fields="files(id, name)"
            ).execute()
            files = results.get('files', [])
            
            if not files:
                st.warning("⚠️ No resumes found in that folder.")
                st.stop()

            # 3. Check OneDrive
            st.write("📂 Checking OneDrive for duplicates...")
            existing_on_onedrive = connectors.get_onedrive_files(ms_client_id, g_target_path)
            
            # 4. Sync Loop
            synced_count = 0
            for file in files:
                file_name = file['name']
                if file_name in existing_on_onedrive:
                    st.write(f"⏩ Skipping **{file_name}** (Already exists)")
                    continue
                
                st.write(f"⬇️ Downloading **{file_name}**...")
                file_content = connectors.download_from_gdrive(g_service, file['id'])
                
                st.write(f"⬆️ Uploading to OneDrive...")
                status_code = connectors.upload_to_onedrive(file_content, file_name, ms_client_id, g_target_path)
                
                if status_code in [200, 201]:
                    synced_count += 1
            
            status.update(label="✅ Google Drive Sync Complete!", state="complete", expanded=False)
        st.success(f"Successfully synced {synced_count} new resumes!")


# ==========================================
# TAB 2: GLOBAL GITHUB SEARCH
# ==========================================
with tab2:
    st.header("Global GitHub to OneDrive")
    st.write("Scour the entire open-source GitHub community for public resumes.")
    
    # Settings
    gh_token = st.text_input("GitHub Personal Access Token", type="password", value=st.secrets.get("GITHUB_TOKEN", ""))
    
    col3, col4 = st.columns(2)
    with col3:
        gh_category = st.selectbox("Search Keyword", ["Java", "Python", "React", "Data Science"], key="gh_cat")
        max_downloads = st.slider("Max Resumes to Download", min_value=1, max_value=50, value=10)
    with col4:
        gh_target_path = st.text_input("OneDrive Target Folder", value=f"Resumes/Global_{gh_category}", key="gh_path")

    # Action Button
    if st.button(f"🌍 Scrape World for '{gh_category}' Resumes"):
        
        # PRE-FLIGHT CHECKS
        if not gh_token:
            st.error("❌ GitHub Token is required to search globally.")
            st.stop()
        if not ms_connected:
            st.error("❌ Please connect Microsoft OneDrive in the sidebar first.")
            st.stop()
            
        with st.status(f"Searching GitHub globally for '{gh_category}'...", expanded=True) as status:
            
            # 1. Fetch from GitHub
            st.write(f"🔍 Searching... (Limit: {max_downloads} files)")
            github_files = connectors.get_global_github_resumes(gh_token, gh_category, max_downloads)
            
            if not github_files:
                st.warning(f"⚠️ No public resumes found for '{gh_category}'.")
                st.stop()
            st.write(f"✅ Downloaded {len(github_files)} matching resumes!")
                
            # 2. Check OneDrive
            st.write("📂 Checking OneDrive for duplicates...")
            existing_on_onedrive = connectors.get_onedrive_files(ms_client_id, gh_target_path)
            
            # 3. Sync Loop
            synced_count = 0
            for file in github_files:
                file_name = file['name']
                if file_name in existing_on_onedrive:
                    st.write(f"⏩ Skipping **{file_name}** (Already exists)")
                    continue
                    
                st.write(f"⬆️ Uploading **{file_name}** to OneDrive...")
                status_code = connectors.upload_to_onedrive(file['content'], file_name, ms_client_id, gh_target_path)
                
                if status_code in [200, 201]:
                    synced_count += 1
                    
            status.update(label="✅ Global GitHub Sync Complete!", state="complete", expanded=False)
        st.success(f"Successfully scraped and synced {synced_count} global resumes!")