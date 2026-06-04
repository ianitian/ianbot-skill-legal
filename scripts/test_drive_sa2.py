import io
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
FILE_ID = "1dZgTCzf32PlB6WNpEImToyGOH3H0Ndq-"  # not the folder ID

creds = service_account.Credentials.from_service_account_file(
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"], scopes=SCOPES
)
drive = build("drive", "v3", credentials=creds, cache_discovery=False)

request = drive.files().get_media(fileId=FILE_ID, supportsAllDrives=True)
buf = io.BytesIO()
downloader = MediaIoBaseDownload(buf, request)
done = False
while not done:
    _, done = downloader.next_chunk()

data = buf.getvalue()
print(f"Downloaded {len(data)} bytes")
print("PDF OK" if data[:4] == b"%PDF" else "Not a PDF header — check file ID / mime type")
