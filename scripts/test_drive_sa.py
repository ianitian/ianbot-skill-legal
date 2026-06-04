import os
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
creds_path = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
folder_id = os.environ["DRIVE_FOLDER_ID"]

creds = service_account.Credentials.from_service_account_file(creds_path, scopes=SCOPES)
drive = build("drive", "v3", credentials=creds, cache_discovery=False)

q = f"'{folder_id}' in parents and trashed = false"
result = drive.files().list(
    q=q,
    pageSize=20,
    fields="files(id, name, mimeType)",
    supportsAllDrives=True,
    includeItemsFromAllDrives=True,
).execute()

files = result.get("files", [])
print(f"Found {len(files)} item(s) directly under folder {folder_id}:")
for f in files:
    print(f"  {f['mimeType']:40} {f['name'][:60]}  id={f['id']}")
