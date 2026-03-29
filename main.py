from connectors import (
    get_gdrive_service, 
    download_from_gdrive, 
    upload_to_onedrive,
    get_github_resumes,
    get_onedrive_files
)

# --- CONFIG ---
MICROSOFT_CLIENT_ID = 'b4451427-fd56-4294-ba6a-ce454730b3b7'
G_DRIVE_FOLDER_ID = '1McYaWwi54WXJBaZ5ihcxd5uyQttH-I9s'
GITHUB_TOKEN = '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'
GITHUB_REPO = '12345-Sr/Resumes'

def run_sync():
    print("🧠 Starting Smart Sync Agent...")
    
    # Step 1: See what's already in OneDrive
    existing_files = get_onedrive_files(MICROSOFT_CLIENT_ID)
    print(f"📂 Found {len(existing_files)} existing files in OneDrive.")

    # Step 2: Handle Google Drive
    g_service = get_gdrive_service()
    g_files = g_service.files().list(q=f"'{G_DRIVE_FOLDER_ID}' in parents").execute().get('files', [])
    
    for f in g_files:
        if f['name'] in existing_files:
            print(f"⏭️ Skipping {f['name']} (Already in OneDrive)")
            continue
            
        print(f"📥 Syncing from Drive: {f['name']}...")
        content = download_from_gdrive(g_service, f['id'])
        upload_to_onedrive(content, f['name'], MICROSOFT_CLIENT_ID)

    # Step 3: Handle GitHub
    gh_files = get_github_resumes(GITHUB_TOKEN, GITHUB_REPO)
    for f in gh_files:
        if f['name'] in existing_files:
            print(f"⏭️ Skipping {f['name']} (Already in OneDrive)")
            continue
            
        print(f"📥 Syncing from GitHub: {f['name']}...")
        upload_to_onedrive(f['content'], f['name'], MICROSOFT_CLIENT_ID)

    print("🏁 Sync complete!")

if __name__ == "__main__":
    run_sync()