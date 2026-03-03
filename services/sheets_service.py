"""
Google Sheets Database Service for History Storage
Uses Google Sheets as a simple database for storing TTS history metadata
"""

import os
import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# Try to import Google Sheets API
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    SHEETS_AVAILABLE = True
except ImportError:
    SHEETS_AVAILABLE = False
    logger.warning("Google Sheets API not available. Install with: pip install google-api-python-client google-auth")


class SheetsService:
    """Service for storing history metadata in Google Sheets"""
    
    # Column headers for the history sheet
    HEADERS = [
        "id", "text", "voice_id", "voice_name", "model", 
        "language", "characters", "cost", "timestamp", "audio_path"
    ]
    
    def __init__(self, spreadsheet_id: str, credentials_json: str):
        """
        Initialize Google Sheets service
        
        Args:
            spreadsheet_id: The ID from the Google Sheets URL
            credentials_json: JSON string of service account credentials
        """
        self.spreadsheet_id = spreadsheet_id
        self.sheet_name = "History"  # Default sheet name
        self.service = None
        self._initialized = False
        
        if not SHEETS_AVAILABLE:
            logger.error("Google Sheets API not installed")
            return
            
        try:
            # Parse credentials
            creds_dict = json.loads(credentials_json)
            credentials = service_account.Credentials.from_service_account_info(
                creds_dict,
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            
            # Build the service
            self.service = build('sheets', 'v4', credentials=credentials)
            self._initialized = True
            logger.info(f"Google Sheets service initialized for spreadsheet: {spreadsheet_id}")
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid credentials JSON: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize Sheets service: {e}")
    
    @property
    def is_available(self) -> bool:
        """Check if sheets service is available"""
        return self._initialized and self.service is not None
    
    async def ensure_headers(self) -> bool:
        """Ensure the sheet has proper headers"""
        if not self.is_available:
            return False
            
        try:
            # Check if sheet exists and has headers
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.sheet_name}!A1:J1"
            ).execute()
            
            values = result.get('values', [])
            
            if not values or values[0] != self.HEADERS:
                # Set headers
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"{self.sheet_name}!A1:J1",
                    valueInputOption='RAW',
                    body={'values': [self.HEADERS]}
                ).execute()
                logger.info("Sheet headers initialized")
            
            return True
            
        except HttpError as e:
            if e.resp.status == 400:
                # Sheet might not exist, try to create it
                try:
                    self.service.spreadsheets().batchUpdate(
                        spreadsheetId=self.spreadsheet_id,
                        body={
                            'requests': [{
                                'addSheet': {
                                    'properties': {'title': self.sheet_name}
                                }
                            }]
                        }
                    ).execute()
                    # Now add headers
                    self.service.spreadsheets().values().update(
                        spreadsheetId=self.spreadsheet_id,
                        range=f"{self.sheet_name}!A1:J1",
                        valueInputOption='RAW',
                        body={'values': [self.HEADERS]}
                    ).execute()
                    logger.info("Created new sheet with headers")
                    return True
                except Exception as create_error:
                    logger.error(f"Failed to create sheet: {create_error}")
            logger.error(f"Failed to ensure headers: {e}")
            return False
        except Exception as e:
            logger.error(f"Error ensuring headers: {e}")
            return False
    
    async def add_entry(self, entry: Dict[str, Any]) -> bool:
        """
        Add a new history entry to the sheet
        
        Args:
            entry: Dictionary with history entry data
        """
        if not self.is_available:
            logger.warning("Sheets service not available, cannot add entry")
            return False
            
        try:
            # Prepare row data in correct order
            row = [
                entry.get('id', ''),
                entry.get('text', ''),
                entry.get('voice_id', ''),
                entry.get('voice_name', ''),
                entry.get('model', ''),
                entry.get('language', ''),
                str(entry.get('characters', 0)),
                str(entry.get('cost', 0)),
                entry.get('timestamp', ''),
                entry.get('audio_path', '')
            ]
            
            # Append to sheet
            self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.sheet_name}!A:J",
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': [row]}
            ).execute()
            
            logger.info(f"Added entry to sheets: {entry.get('id')}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add entry to sheets: {e}")
            return False
    
    async def get_all_entries(self) -> List[Dict[str, Any]]:
        """Get all history entries from the sheet"""
        if not self.is_available:
            return []
            
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.sheet_name}!A:J"
            ).execute()
            
            values = result.get('values', [])
            
            if len(values) <= 1:  # Only headers or empty
                return []
            
            entries = []
            headers = values[0]
            
            for row in values[1:]:
                # Pad row with empty strings if needed
                while len(row) < len(headers):
                    row.append('')
                    
                entry = {}
                for i, header in enumerate(headers):
                    value = row[i] if i < len(row) else ''
                    # Convert numeric fields
                    if header in ['characters', 'cost']:
                        try:
                            entry[header] = float(value) if '.' in str(value) else int(value)
                        except (ValueError, TypeError):
                            entry[header] = 0
                    else:
                        entry[header] = value
                entries.append(entry)
            
            # Sort by timestamp descending (newest first)
            entries.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            return entries
            
        except Exception as e:
            logger.error(f"Failed to get entries from sheets: {e}")
            return []
    
    async def get_entry_by_id(self, entry_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific entry by ID"""
        entries = await self.get_all_entries()
        for entry in entries:
            if entry.get('id') == entry_id:
                return entry
        return None
    
    async def delete_entry(self, entry_id: str) -> bool:
        """Delete an entry by ID"""
        if not self.is_available:
            return False
            
        try:
            # Get all values to find the row
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.sheet_name}!A:A"
            ).execute()
            
            values = result.get('values', [])
            
            # Find the row with matching ID
            row_index = None
            for i, row in enumerate(values):
                if row and row[0] == entry_id:
                    row_index = i
                    break
            
            if row_index is None:
                logger.warning(f"Entry not found in sheets: {entry_id}")
                return False
            
            # Get sheet ID for the delete request
            sheet_metadata = self.service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id
            ).execute()
            
            sheet_id = None
            for sheet in sheet_metadata.get('sheets', []):
                if sheet['properties']['title'] == self.sheet_name:
                    sheet_id = sheet['properties']['sheetId']
                    break
            
            if sheet_id is None:
                logger.error("Could not find sheet ID")
                return False
            
            # Delete the row
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={
                    'requests': [{
                        'deleteDimension': {
                            'range': {
                                'sheetId': sheet_id,
                                'dimension': 'ROWS',
                                'startIndex': row_index,
                                'endIndex': row_index + 1
                            }
                        }
                    }]
                }
            ).execute()
            
            logger.info(f"Deleted entry from sheets: {entry_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete entry from sheets: {e}")
            return False
    
    async def clear_all(self) -> bool:
        """Clear all entries (keep headers)"""
        if not self.is_available:
            return False
            
        try:
            # Get row count
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.sheet_name}!A:A"
            ).execute()
            
            values = result.get('values', [])
            
            if len(values) <= 1:
                return True  # Only headers, nothing to clear
            
            # Clear all rows except header
            self.service.spreadsheets().values().clear(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.sheet_name}!A2:J"
            ).execute()
            
            logger.info("Cleared all entries from sheets")
            return True
            
        except Exception as e:
            logger.error(f"Failed to clear sheets: {e}")
            return False
    
    # ==================== AI USAGE TRACKING ====================
    
    USAGE_SHEET_NAME = "Usage"
    USAGE_HEADERS = [
        "timestamp", "service", "type", "input_tokens", "output_tokens", 
        "characters", "cost_usd", "description"
    ]
    
    async def ensure_usage_sheet(self) -> bool:
        """Ensure the Usage sheet exists with proper headers"""
        if not self.is_available:
            return False
            
        try:
            # Try to get the Usage sheet
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.USAGE_SHEET_NAME}!A1:H1"
            ).execute()
            
            values = result.get('values', [])
            
            if not values or values[0] != self.USAGE_HEADERS:
                # Set headers
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"{self.USAGE_SHEET_NAME}!A1:H1",
                    valueInputOption='RAW',
                    body={'values': [self.USAGE_HEADERS]}
                ).execute()
                logger.info("Usage sheet headers initialized")
            
            return True
            
        except HttpError as e:
            if e.resp.status == 400:
                # Sheet doesn't exist, create it
                try:
                    self.service.spreadsheets().batchUpdate(
                        spreadsheetId=self.spreadsheet_id,
                        body={
                            'requests': [{
                                'addSheet': {
                                    'properties': {'title': self.USAGE_SHEET_NAME}
                                }
                            }]
                        }
                    ).execute()
                    # Now add headers
                    self.service.spreadsheets().values().update(
                        spreadsheetId=self.spreadsheet_id,
                        range=f"{self.USAGE_SHEET_NAME}!A1:H1",
                        valueInputOption='RAW',
                        body={'values': [self.USAGE_HEADERS]}
                    ).execute()
                    logger.info("Created Usage sheet with headers")
                    return True
                except Exception as create_error:
                    logger.error(f"Failed to create Usage sheet: {create_error}")
            logger.error(f"Failed to ensure Usage headers: {e}")
            return False
        except Exception as e:
            logger.error(f"Error ensuring Usage headers: {e}")
            return False
    
    async def add_usage_entry(self, service: str, usage_type: str, 
                              input_tokens: int = 0, output_tokens: int = 0,
                              characters: int = 0, cost_usd: float = 0.0,
                              description: str = "") -> bool:
        """
        Add a usage entry to the Usage sheet
        
        Args:
            service: "claude" or "elevenlabs"
            usage_type: "enhancement" for Claude, "tts" for ElevenLabs
            input_tokens: Input tokens (Claude only)
            output_tokens: Output tokens (Claude only)
            characters: Characters used (ElevenLabs only)
            cost_usd: Cost in USD
            description: Optional description
        """
        if not self.is_available:
            logger.warning("Sheets service not available, cannot add usage entry")
            return False
        
        await self.ensure_usage_sheet()
            
        try:
            timestamp = datetime.now().isoformat()
            row = [
                timestamp,
                service,
                usage_type,
                str(input_tokens),
                str(output_tokens),
                str(characters),
                str(cost_usd),
                description
            ]
            
            self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.USAGE_SHEET_NAME}!A:H",
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': [row]}
            ).execute()
            
            logger.info(f"Added {service} usage entry: ${cost_usd:.6f}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add usage entry: {e}")
            return False
    
    async def get_usage_totals(self) -> Dict[str, Any]:
        """
        Get cumulative usage totals from the Usage sheet
        
        Returns dict with:
            - claude_requests, claude_input_tokens, claude_output_tokens, claude_cost_usd
            - elevenlabs_requests, elevenlabs_characters, elevenlabs_cost_usd
            - total_cost_usd
        """
        if not self.is_available:
            return self._empty_usage_totals()
        
        await self.ensure_usage_sheet()
            
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.USAGE_SHEET_NAME}!A:H"
            ).execute()
            
            values = result.get('values', [])
            
            if len(values) <= 1:  # Only headers or empty
                return self._empty_usage_totals()
            
            totals = self._empty_usage_totals()
            
            for row in values[1:]:
                if len(row) < 7:
                    continue
                    
                service = row[1] if len(row) > 1 else ""
                input_tokens = self._safe_int(row[3]) if len(row) > 3 else 0
                output_tokens = self._safe_int(row[4]) if len(row) > 4 else 0
                characters = self._safe_int(row[5]) if len(row) > 5 else 0
                cost = self._safe_float(row[6]) if len(row) > 6 else 0.0
                
                if service == "claude":
                    totals["claude_requests"] += 1
                    totals["claude_input_tokens"] += input_tokens
                    totals["claude_output_tokens"] += output_tokens
                    totals["claude_cost_usd"] += cost
                elif service == "elevenlabs":
                    totals["elevenlabs_requests"] += 1
                    totals["elevenlabs_characters"] += characters
                    totals["elevenlabs_cost_usd"] += cost
                
                totals["total_cost_usd"] += cost
            
            return totals
            
        except Exception as e:
            logger.error(f"Failed to get usage totals: {e}")
            return self._empty_usage_totals()
    
    def _empty_usage_totals(self) -> Dict[str, Any]:
        """Return empty usage totals structure"""
        return {
            "claude_requests": 0,
            "claude_input_tokens": 0,
            "claude_output_tokens": 0,
            "claude_cost_usd": 0.0,
            "elevenlabs_requests": 0,
            "elevenlabs_characters": 0,
            "elevenlabs_cost_usd": 0.0,
            "total_cost_usd": 0.0
        }
    
    def _safe_int(self, value) -> int:
        """Safely convert to int"""
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return 0
    
    def _safe_float(self, value) -> float:
        """Safely convert to float"""
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0


class LocalHistoryFallback:
    """Local JSON file fallback when Sheets is not available"""
    
    def __init__(self, history_file: str = "history.json"):
        self.history_file = history_file
        self._history = []
        self._load_history()
    
    def _load_history(self):
        """Load history from file"""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r') as f:
                    self._history = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load history: {e}")
            self._history = []
    
    def _save_history(self):
        """Save history to file"""
        try:
            with open(self.history_file, 'w') as f:
                json.dump(self._history, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save history: {e}")
    
    @property
    def is_available(self) -> bool:
        return True
    
    async def ensure_headers(self) -> bool:
        return True
    
    async def add_entry(self, entry: Dict[str, Any]) -> bool:
        self._history.insert(0, entry)  # Add to beginning
        self._save_history()
        return True
    
    async def get_all_entries(self) -> List[Dict[str, Any]]:
        return self._history
    
    async def get_entry_by_id(self, entry_id: str) -> Optional[Dict[str, Any]]:
        for entry in self._history:
            if entry.get('id') == entry_id:
                return entry
        return None
    
    async def delete_entry(self, entry_id: str) -> bool:
        for i, entry in enumerate(self._history):
            if entry.get('id') == entry_id:
                self._history.pop(i)
                self._save_history()
                return True
        return False
    
    async def clear_all(self) -> bool:
        self._history = []
        self._save_history()
        return True
    
    # ==================== AI USAGE TRACKING (LOCAL FALLBACK) ====================
    
    def _load_usage(self) -> List[Dict]:
        """Load usage from file"""
        usage_file = "usage.json"
        try:
            if os.path.exists(usage_file):
                with open(usage_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load usage: {e}")
        return []
    
    def _save_usage(self, usage: List[Dict]):
        """Save usage to file"""
        usage_file = "usage.json"
        try:
            with open(usage_file, 'w') as f:
                json.dump(usage, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save usage: {e}")
    
    async def ensure_usage_sheet(self) -> bool:
        return True
    
    async def add_usage_entry(self, service: str, usage_type: str, 
                              input_tokens: int = 0, output_tokens: int = 0,
                              characters: int = 0, cost_usd: float = 0.0,
                              description: str = "") -> bool:
        """Add a usage entry to local storage"""
        usage = self._load_usage()
        usage.append({
            "timestamp": datetime.now().isoformat(),
            "service": service,
            "type": usage_type,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "characters": characters,
            "cost_usd": cost_usd,
            "description": description
        })
        self._save_usage(usage)
        logger.info(f"Added {service} usage entry: ${cost_usd:.6f}")
        return True
    
    async def get_usage_totals(self) -> Dict[str, Any]:
        """Get cumulative usage totals from local storage"""
        usage = self._load_usage()
        
        totals = {
            "claude_requests": 0,
            "claude_input_tokens": 0,
            "claude_output_tokens": 0,
            "claude_cost_usd": 0.0,
            "elevenlabs_requests": 0,
            "elevenlabs_characters": 0,
            "elevenlabs_cost_usd": 0.0,
            "total_cost_usd": 0.0
        }
        
        for entry in usage:
            service = entry.get("service", "")
            cost = entry.get("cost_usd", 0.0)
            
            if service == "claude":
                totals["claude_requests"] += 1
                totals["claude_input_tokens"] += entry.get("input_tokens", 0)
                totals["claude_output_tokens"] += entry.get("output_tokens", 0)
                totals["claude_cost_usd"] += cost
            elif service == "elevenlabs":
                totals["elevenlabs_requests"] += 1
                totals["elevenlabs_characters"] += entry.get("characters", 0)
                totals["elevenlabs_cost_usd"] += cost
            
            totals["total_cost_usd"] += cost
        
        return totals


def get_sheets_service():
    """
    Factory function to get sheets service or fallback
    
    Returns SheetsService if credentials are configured, otherwise LocalHistoryFallback
    """
    spreadsheet_id = os.environ.get('GOOGLE_SHEETS_ID')
    credentials_json = os.environ.get('GCS_CREDENTIALS_JSON')  # Reuse GCS credentials
    
    if spreadsheet_id and credentials_json and SHEETS_AVAILABLE:
        service = SheetsService(spreadsheet_id, credentials_json)
        if service.is_available:
            logger.info("Using Google Sheets for history storage")
            return service
    
    logger.info("Using local JSON file for history storage")
    return LocalHistoryFallback()
