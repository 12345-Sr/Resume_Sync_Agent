# 🎯 Resume Sync AI: Categorized Resume Sync Agent

An automated pipeline that monitors **Google Drive** and **GitHub** for new resumes, categorizes them by skill (Java, Python, React, etc.), and synchronizes them into a centralized, organized **Microsoft OneDrive** repository.

---

## 🚀 Features

* **Smart Categorization:** Syncs only the specific subfolders you choose (e.g., only "Java" resumes).
* **Multi-Source Integration:** Pulls data from Google Drive API and GitHub API simultaneously.
* **De-duplication:** Automatically checks OneDrive before uploading to prevent file clutter.
* **Streamlit UI:** A clean, web-based dashboard to manage configurations and trigger syncs.
* **Cloud Ready:** Fully compatible with GitHub Codespaces and Streamlit Community Cloud.

---

## 🛠️ Tech Stack

* **Language:** Python 3.10+
* **UI Framework:** [Streamlit](https://streamlit.io/)
* **APIs:** * Google Drive API v3
    * Microsoft Graph API (MSAL)
    * GitHub REST API (PyGithub)

---

## 📂 Project Structure

```text
├── app.py                # Main Streamlit UI and Orchestration logic
├── connectors.py         # Specialized API tools for Drive, OneDrive, and GitHub
├── main.py               # Local configuration settings (Client IDs & Tokens)
├── requirements.txt      # Python dependencies
└── credentials.json      # Google OAuth 2.0 Desktop credentials (User provided)