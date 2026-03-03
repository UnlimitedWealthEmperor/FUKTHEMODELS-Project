"""
Google Cloud Storage Service
Handles audio file storage in GCS with local fallback
"""

import os
import uuid
from pathlib import Path
from typing import Optional, BinaryIO
from datetime import datetime, timedelta

# Try to import GCS library
try:
    from google.cloud import storage
    from google.oauth2 import service_account
    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False
    print("⚠ google-cloud-storage not installed - using local storage")


class StorageService:
    """
    Handles file storage - uses GCS if configured, falls back to local storage
    """
    
    def __init__(
        self,
        bucket_name: Optional[str] = None,
        credentials_json: Optional[str] = None,
        local_fallback_dir: Optional[Path] = None
    ):
        self.bucket_name = bucket_name or os.getenv("GCS_BUCKET_NAME")
        self.credentials_json = credentials_json or os.getenv("GCS_CREDENTIALS_JSON")
        self.local_dir = local_fallback_dir or Path(__file__).parent.parent / "generated"
        
        self.client: Optional[storage.Client] = None
        self.bucket = None
        self.use_gcs = False
        
        # Try to initialize GCS
        if GCS_AVAILABLE and self.bucket_name and self.credentials_json:
            try:
                self._init_gcs()
                self.use_gcs = True
                print(f"✓ GCS storage initialized (bucket: {self.bucket_name})")
            except Exception as e:
                print(f"⚠ GCS initialization failed: {e}")
                print("  Falling back to local storage")
        else:
            if not GCS_AVAILABLE:
                print("⚠ GCS library not available - using local storage")
            elif not self.bucket_name:
                print("⚠ GCS_BUCKET_NAME not set - using local storage")
            elif not self.credentials_json:
                print("⚠ GCS_CREDENTIALS_JSON not set - using local storage")
        
        # Ensure local directory exists as fallback
        self.local_dir.mkdir(exist_ok=True)
    
    def _init_gcs(self):
        """Initialize GCS client from JSON credentials"""
        import json
        
        # Parse credentials JSON (can be string or file path)
        if self.credentials_json.startswith('{'):
            # It's a JSON string
            creds_dict = json.loads(self.credentials_json)
        else:
            # It's a file path
            with open(self.credentials_json) as f:
                creds_dict = json.load(f)
        
        credentials = service_account.Credentials.from_service_account_info(creds_dict)
        self.client = storage.Client(credentials=credentials, project=creds_dict.get('project_id'))
        self.bucket = self.client.bucket(self.bucket_name)
    
    def save_audio(self, audio_data: bytes, filename: Optional[str] = None) -> str:
        """
        Save audio file and return the filename/path
        
        Args:
            audio_data: Raw audio bytes
            filename: Optional filename (will generate if not provided)
            
        Returns:
            Filename that was saved
        """
        if not filename:
            filename = f"gen_{uuid.uuid4().hex[:12]}.mp3"
        
        if self.use_gcs:
            return self._save_to_gcs(audio_data, filename)
        else:
            return self._save_to_local(audio_data, filename)
    
    def _save_to_gcs(self, audio_data: bytes, filename: str) -> str:
        """Save to Google Cloud Storage"""
        blob = self.bucket.blob(f"audio/{filename}")
        blob.upload_from_string(audio_data, content_type="audio/mpeg")
        return filename
    
    def _save_to_local(self, audio_data: bytes, filename: str) -> str:
        """Save to local filesystem"""
        filepath = self.local_dir / filename
        with open(filepath, 'wb') as f:
            f.write(audio_data)
        return filename
    
    def get_audio(self, filename: str) -> Optional[bytes]:
        """
        Retrieve audio file
        
        Args:
            filename: The filename to retrieve
            
        Returns:
            Audio bytes or None if not found
        """
        if self.use_gcs:
            return self._get_from_gcs(filename)
        else:
            return self._get_from_local(filename)
    
    def _get_from_gcs(self, filename: str) -> Optional[bytes]:
        """Get from Google Cloud Storage"""
        try:
            blob = self.bucket.blob(f"audio/{filename}")
            return blob.download_as_bytes()
        except Exception as e:
            print(f"Error downloading from GCS: {e}")
            return None
    
    def _get_from_local(self, filename: str) -> Optional[bytes]:
        """Get from local filesystem"""
        filepath = self.local_dir / filename
        if filepath.exists():
            with open(filepath, 'rb') as f:
                return f.read()
        return None
    
    def get_audio_url(self, filename: str, expiration_minutes: int = 60) -> Optional[str]:
        """
        Get a URL to access the audio file
        
        For GCS: Returns a signed URL that expires
        For local: Returns None (use the API endpoint instead)
        
        Args:
            filename: The filename
            expiration_minutes: How long the URL should be valid (GCS only)
            
        Returns:
            URL string or None
        """
        if self.use_gcs:
            try:
                blob = self.bucket.blob(f"audio/{filename}")
                url = blob.generate_signed_url(
                    expiration=timedelta(minutes=expiration_minutes),
                    method="GET"
                )
                return url
            except Exception as e:
                print(f"Error generating signed URL: {e}")
                return None
        return None
    
    def delete_audio(self, filename: str) -> bool:
        """
        Delete an audio file
        
        Args:
            filename: The filename to delete
            
        Returns:
            True if deleted, False otherwise
        """
        if self.use_gcs:
            return self._delete_from_gcs(filename)
        else:
            return self._delete_from_local(filename)
    
    def _delete_from_gcs(self, filename: str) -> bool:
        """Delete from Google Cloud Storage"""
        try:
            blob = self.bucket.blob(f"audio/{filename}")
            blob.delete()
            return True
        except Exception as e:
            print(f"Error deleting from GCS: {e}")
            return False
    
    def _delete_from_local(self, filename: str) -> bool:
        """Delete from local filesystem"""
        filepath = self.local_dir / filename
        if filepath.exists():
            filepath.unlink()
            return True
        return False
    
    def list_audio_files(self, prefix: str = "") -> list:
        """
        List audio files
        
        Args:
            prefix: Optional prefix to filter files
            
        Returns:
            List of filenames
        """
        if self.use_gcs:
            try:
                blobs = self.bucket.list_blobs(prefix=f"audio/{prefix}")
                return [blob.name.replace("audio/", "") for blob in blobs]
            except Exception as e:
                print(f"Error listing GCS files: {e}")
                return []
        else:
            files = list(self.local_dir.glob(f"{prefix}*.mp3"))
            return [f.name for f in files]
    
    @property
    def storage_type(self) -> str:
        """Return the current storage type"""
        return "gcs" if self.use_gcs else "local"


# Singleton instance
_storage_service: Optional[StorageService] = None


def get_storage_service() -> StorageService:
    """Get or create the storage service singleton"""
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service
