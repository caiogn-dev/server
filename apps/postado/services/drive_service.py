import io
import logging
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/drive']
SERVICE_ACCOUNT_FILE = os.environ.get('POSTADO_GOOGLE_SERVICE_ACCOUNT_JSON', '')
ROOT_FOLDER_ID = os.environ.get('POSTADO_DRIVE_ROOT_FOLDER_ID', '')


class DriveService:
    def __init__(self):
        self._service = None

    def _get_service(self):
        if self._service is None:
            creds = service_account.Credentials.from_service_account_file(
                SERVICE_ACCOUNT_FILE, scopes=SCOPES
            )
            self._service = build('drive', 'v3', credentials=creds)
        return self._service

    def create_client_folder(self, business_name: str) -> tuple:
        svc = self._get_service()
        metadata = {
            'name': business_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [ROOT_FOLDER_ID] if ROOT_FOLDER_ID else [],
        }
        result = svc.files().create(
            body=metadata,
            fields='id,webViewLink'
        ).execute()
        folder_id = result['id']
        svc.permissions().create(
            fileId=folder_id,
            body={'type': 'anyone', 'role': 'reader'},
        ).execute()
        return folder_id, result.get('webViewLink', '')

    def create_subfolder(self, name: str, parent_id: str) -> str:
        svc = self._get_service()
        metadata = {
            'name': name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id],
        }
        result = svc.files().create(body=metadata, fields='id').execute()
        return result['id']

    def upload_image(self, image_bytes: bytes, filename: str, folder_id: str) -> tuple:
        svc = self._get_service()
        metadata = {'name': filename, 'parents': [folder_id]}
        media = MediaIoBaseUpload(io.BytesIO(image_bytes), mimetype='image/png')
        result = svc.files().create(
            body=metadata,
            media_body=media,
            fields='id,webViewLink'
        ).execute()
        return result['id'], result.get('webViewLink', '')
