import os
import jwt
import bcrypt
import uuid
import json
from datetime import datetime, timedelta
from supabase import create_client, Client
from functools import wraps
from flask import request, jsonify, current_app
from config import Config
import logging

logger = logging.getLogger(__name__)

class AuthService:
    def __init__(self):
        # Set up local storage directory
        self.local_storage_path = os.environ.get('PDF_STORAGE_PATH', './pdf_storage')
        os.makedirs(self.local_storage_path, exist_ok=True)
        
        # Set up background music storage directory
        self.music_storage_path = os.environ.get('MUSIC_STORAGE_PATH', './music_storage')
        os.makedirs(self.music_storage_path, exist_ok=True)
        
        if Config.SUPABASE_URL and Config.SUPABASE_ANON_KEY and Config.SUPABASE_URL != '' and Config.SUPABASE_ANON_KEY != '':
            try:
                # Use anon key for auth operations
                self.supabase: Client = create_client(Config.SUPABASE_URL, Config.SUPABASE_ANON_KEY)
                # Use service role key for database operations (bypasses RLS)
                if Config.SUPABASE_SERVICE_ROLE_KEY:
                    self.supabase_admin: Client = create_client(Config.SUPABASE_URL, Config.SUPABASE_SERVICE_ROLE_KEY)
                else:
                    self.supabase_admin = self.supabase
                logger.info("Supabase client initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize Supabase client: {e}")
                self.supabase = None
                self.supabase_admin = None
        else:
            logger.warning("Supabase credentials not configured - running in development mode")
            self.supabase = None
            self.supabase_admin = None

    def _get_user_storage_path(self, user_id: str):
        """Get the local storage path for a specific user"""
        user_path = os.path.join(self.local_storage_path, user_id)
        os.makedirs(user_path, exist_ok=True)
        return user_path

    def _get_user_music_storage_path(self, user_id: str):
        """Get the local music storage path for a specific user"""
        user_music_path = os.path.join(self.music_storage_path, user_id)
        os.makedirs(user_music_path, exist_ok=True)
        return user_music_path

    def _get_cache_file_path(self, user_id: str, file_id: str):
        """Get the cache file path for PDF word data"""
        user_storage_path = self._get_user_storage_path(user_id)
        return os.path.join(user_storage_path, f"{file_id}_words.json")

    def _save_word_cache(self, user_id: str, file_id: str, word_data: list):
        """Save extracted word data to cache file"""
        try:
            cache_file_path = self._get_cache_file_path(user_id, file_id)
            cache_data = {
                'word_data': word_data,
                'cached_at': datetime.utcnow().isoformat(),
                'word_count': len(word_data)
            }
            
            with open(cache_file_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Cached word data for file {file_id}: {len(word_data)} words")
            return True
        except Exception as e:
            logger.error(f"Error saving word cache: {e}")
            return False

    def _load_word_cache(self, user_id: str, file_id: str):
        """Load cached word data if available"""
        try:
            cache_file_path = self._get_cache_file_path(user_id, file_id)
            
            if not os.path.exists(cache_file_path):
                return None
            
            with open(cache_file_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            logger.info(f"Loaded cached word data for file {file_id}: {cache_data.get('word_count', 0)} words")
            return cache_data
        except Exception as e:
            logger.error(f"Error loading word cache: {e}")
            return None

    def _delete_word_cache(self, user_id: str, file_id: str):
        """Delete cached word data"""
        try:
            cache_file_path = self._get_cache_file_path(user_id, file_id)
            if os.path.exists(cache_file_path):
                os.remove(cache_file_path)
                logger.info(f"Deleted word cache for file {file_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting word cache: {e}")
            return False

    def get_cached_words(self, user_id: str, file_id: str):
        """Get cached word data for a PDF file"""
        try:
            cache_data = self._load_word_cache(user_id, file_id)
            if cache_data:
                return {
                    'success': True,
                    'words': cache_data['word_data'],
                    'cached': True,
                    'cached_at': cache_data['cached_at'],
                    'word_count': cache_data['word_count']
                }
            else:
                return {
                    'success': True,
                    'words': [],
                    'cached': False
                }
        except Exception as e:
            logger.error(f"Error getting cached words: {e}")
            return {'error': str(e)}, 500

    def save_word_cache(self, user_id: str, file_id: str, word_data: list):
        """Save word data to cache"""
        try:
            success = self._save_word_cache(user_id, file_id, word_data)
            if success:
                return {'success': True, 'cached_words': len(word_data)}
            else:
                return {'error': 'Failed to cache word data'}, 500
        except Exception as e:
            logger.error(f"Error saving word cache: {e}")
            return {'error': str(e)}, 500

    def _save_pdf_to_local_storage(self, user_id: str, filename: str, file_data: bytes):
        """Save PDF file to local storage"""
        try:
            user_storage_path = self._get_user_storage_path(user_id)
            
            # Generate unique filename to avoid conflicts
            file_id = str(uuid.uuid4())
            file_extension = os.path.splitext(filename)[1]
            local_filename = f"{file_id}{file_extension}"
            file_path = os.path.join(user_storage_path, local_filename)
            
            # Write file to disk
            with open(file_path, 'wb') as f:
                f.write(file_data)
            
            return {
                'file_id': file_id,
                'local_filename': local_filename,
                'file_path': file_path
            }
        except Exception as e:
            logger.error(f"Error saving PDF to local storage: {e}")
            raise

    def _get_pdf_from_local_storage(self, user_id: str, file_id: str, filename: str):
        """Get PDF file from local storage"""
        try:
            user_storage_path = self._get_user_storage_path(user_id)
            file_path = os.path.join(user_storage_path, filename)
            
            if os.path.exists(file_path):
                with open(file_path, 'rb') as f:
                    return f.read()
            else:
                return None
        except Exception as e:
            logger.error(f"Error getting PDF from local storage: {e}")
            return None

    def _delete_pdf_from_local_storage(self, user_id: str, filename: str):
        """Delete PDF file from local storage"""
        try:
            user_storage_path = self._get_user_storage_path(user_id)
            file_path = os.path.join(user_storage_path, filename)
            
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting PDF from local storage: {e}")
            return False

    def create_user(self, email: str, password: str, name: str = None):
        """Create a new user account"""
        try:
            if not self.supabase:
                return {'error': 'Authentication service not configured'}, 500
            
            # Sign up user with Supabase Auth
            response = self.supabase.auth.sign_up({
                "email": email,
                "password": password,
                "options": {
                    "data": {"name": name} if name else {}
                }
            })
            
            if response.user:
                # Create user profile in our users table
                user_data = {
                    'id': response.user.id,
                    'email': email,
                    'name': name or email.split('@')[0],
                    'created_at': datetime.utcnow().isoformat()
                }
                
                self.supabase_admin.table('users').insert(user_data).execute()
                
                return {
                    'success': True,
                    'user': {
                        'id': response.user.id,
                        'email': email,
                        'name': name or email.split('@')[0]
                    }
                }
            else:
                return {'error': 'Failed to create user'}, 400
                
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            return {'error': str(e)}, 500

    def authenticate_user(self, email: str, password: str):
        """Authenticate user and return JWT token"""
        try:
            if not self.supabase:
                return {'error': 'Authentication service not configured'}, 500
            
            # Sign in with Supabase
            response = self.supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            
            if response.user and response.session:
                # Get user profile
                user_profile = self.supabase_admin.table('users').select('*').eq('id', response.user.id).execute()
                
                if user_profile.data:
                    user_data = user_profile.data[0]
                    
                    # Create custom JWT token
                    token_payload = {
                        'user_id': response.user.id,
                        'email': response.user.email,
                        'exp': datetime.utcnow() + timedelta(seconds=Config.JWT_ACCESS_TOKEN_EXPIRES)
                    }
                    
                    token = jwt.encode(token_payload, Config.JWT_SECRET_KEY, algorithm='HS256')
                    
                    return {
                        'success': True,
                        'token': token,
                        'user': {
                            'id': user_data['id'],
                            'email': user_data['email'],
                            'name': user_data['name']
                        }
                    }
                else:
                    return {'error': 'User profile not found'}, 404
            else:
                return {'error': 'Invalid credentials'}, 401
                
        except Exception as e:
            logger.error(f"Error authenticating user: {e}")
            return {'error': 'Authentication failed'}, 401

    def verify_token(self, token: str):
        """Verify JWT token and return user data"""
        try:
            payload = jwt.decode(token, Config.JWT_SECRET_KEY, algorithms=['HS256'])
            user_id = payload.get('user_id')
            
            if user_id:
                # Get user profile
                user_profile = self.supabase_admin.table('users').select('*').eq('id', user_id).execute()
                
                if user_profile.data:
                    return {
                        'success': True,
                        'user': user_profile.data[0]
                    }
            
            return {'error': 'Invalid token'}, 401
            
        except jwt.ExpiredSignatureError:
            return {'error': 'Token expired'}, 401
        except jwt.InvalidTokenError:
            return {'error': 'Invalid token'}, 401

    def get_user_pdfs(self, user_id: str):
        """Get all PDFs for a specific user"""
        try:
            pdfs = self.supabase_admin.table('user_pdfs').select('*').eq('user_id', user_id).order('created_at', desc=True).execute()
            return {'success': True, 'pdfs': pdfs.data}
        except Exception as e:
            logger.error(f"Error getting user PDFs: {e}")
            return {'error': str(e)}, 500

    def save_user_pdf(self, user_id: str, filename: str, file_data: bytes):
        """Save PDF file locally and metadata in database"""
        try:
            if not self.supabase:
                return {'error': 'Authentication service not configured'}, 500
            
            # Save file to local storage
            storage_result = self._save_pdf_to_local_storage(user_id, filename, file_data)
            
            # Save PDF metadata to database (without file content)
            pdf_data = {
                'user_id': user_id,
                'filename': filename,
                'file_id': storage_result['file_id'],
                'local_filename': storage_result['local_filename'],
                'file_size': len(file_data),
                'created_at': datetime.utcnow().isoformat()
            }
            
            db_response = self.supabase_admin.table('user_pdfs').insert(pdf_data).execute()
            return {'success': True, 'pdf': db_response.data[0]}
                
        except Exception as e:
            logger.error(f"Error saving user PDF: {e}")
            return {'error': str(e)}, 500

    def get_user_pdf_file(self, user_id: str, file_id: str):
        """Get PDF file content from local storage"""
        try:
            if not self.supabase:
                return {'error': 'Authentication service not configured'}, 500
            
            # Get PDF metadata from database
            pdf_record = self.supabase_admin.table('user_pdfs').select('*').eq('user_id', user_id).eq('file_id', file_id).execute()
            
            if not pdf_record.data:
                return {'error': 'PDF not found'}, 404
            
            pdf_metadata = pdf_record.data[0]
            
            # Get file content from local storage
            file_data = self._get_pdf_from_local_storage(user_id, file_id, pdf_metadata['local_filename'])
            
            if file_data is None:
                return {'error': 'PDF file not found in storage'}, 404
            
            return {
                'success': True,
                'file_data': file_data,
                'metadata': pdf_metadata
            }
        except Exception as e:
            logger.error(f"Error getting user PDF file: {e}")
            return {'error': str(e)}, 500

    def delete_user_pdf(self, user_id: str, file_id: str):
        """Delete PDF file and all associated metadata"""
        try:
            if not self.supabase:
                return {'error': 'Authentication service not configured'}, 500
            
            # Get PDF metadata
            pdf_record = self.supabase_admin.table('user_pdfs').select('*').eq('user_id', user_id).eq('file_id', file_id).execute()
            
            if not pdf_record.data:
                return {'error': 'PDF not found'}, 404
            
            pdf_metadata = pdf_record.data[0]
            logger.info(f"Starting deletion of PDF: {pdf_metadata['filename']} (ID: {file_id}) for user {user_id}")
            
            deletion_summary = {
                'local_file_deleted': False,
                'word_cache_deleted': False,
                'reading_progress_deleted': False,
                'metadata_deleted': False,
                'progress_records_count': 0
            }
            
            # 1. Delete from local storage first
            try:
                if self._delete_pdf_from_local_storage(user_id, pdf_metadata['local_filename']):
                    deletion_summary['local_file_deleted'] = True
                    logger.info(f"✓ Deleted local file: {pdf_metadata['local_filename']}")
                else:
                    logger.warning(f"⚠ Local file not found: {pdf_metadata['local_filename']}")
            except Exception as storage_error:
                logger.warning(f"⚠ Failed to delete local file: {storage_error}")
                # Continue with database cleanup even if file deletion fails
            
            # 2. Delete cached word data
            try:
                if self._delete_word_cache(user_id, file_id):
                    deletion_summary['word_cache_deleted'] = True
                    logger.info(f"✓ Deleted cached word data for file: {file_id}")
                else:
                    logger.info(f"⚠ No word cache found for file: {file_id}")
            except Exception as cache_error:
                logger.warning(f"⚠ Failed to delete word cache: {cache_error}")
                # Continue with cleanup even if cache deletion fails
            
            # 3. Delete associated reading progress (CASCADE should handle this, but being explicit)
            try:
                progress_result = self.supabase_admin.table('reading_progress').delete().eq('user_id', user_id).eq('pdf_id', file_id).execute()
                progress_count = len(progress_result.data) if progress_result.data else 0
                deletion_summary['progress_records_count'] = progress_count
                deletion_summary['reading_progress_deleted'] = True
                logger.info(f"✓ Deleted {progress_count} reading progress record(s)")
            except Exception as progress_error:
                logger.warning(f"⚠ Failed to delete reading progress: {progress_error}")
            
            # 4. Delete metadata from database (this should cascade to remaining reading progress)
            try:
                delete_result = self.supabase_admin.table('user_pdfs').delete().eq('user_id', user_id).eq('file_id', file_id).execute()
                pdf_records_deleted = len(delete_result.data) if delete_result.data else 0
                
                if pdf_records_deleted > 0:
                    deletion_summary['metadata_deleted'] = True
                    logger.info(f"✓ Deleted {pdf_records_deleted} PDF metadata record(s)")
                else:
                    logger.warning(f"⚠ No PDF metadata records were deleted for file_id: {file_id}")
                    return {'error': 'No records were deleted'}, 404
                    
            except Exception as db_error:
                logger.error(f"✗ Failed to delete PDF metadata: {db_error}")
                return {'error': f'Database deletion failed: {str(db_error)}'}, 500
            
            # 5. Verification step - ensure complete cleanup
            try:
                # Check if PDF metadata still exists
                pdf_verification = self.supabase_admin.table('user_pdfs').select('*').eq('user_id', user_id).eq('file_id', file_id).execute()
                if pdf_verification.data:
                    logger.error(f"✗ PDF metadata still exists after deletion attempt: {file_id}")
                    return {'error': 'PDF deletion failed - metadata still exists'}, 500
                
                # Check if reading progress still exists
                progress_verification = self.supabase_admin.table('reading_progress').select('*').eq('user_id', user_id).eq('pdf_id', file_id).execute()
                if progress_verification.data:
                    logger.warning(f"⚠ Orphaned reading progress still exists for file: {file_id}")
                    # Try to clean it up
                    orphan_cleanup = self.supabase_admin.table('reading_progress').delete().eq('pdf_id', file_id).execute()
                    logger.info(f"✓ Cleaned up {len(orphan_cleanup.data) if orphan_cleanup.data else 0} orphaned reading progress records")
                
                # Run the orphaned cleanup function for good measure
                self.supabase_admin.rpc('cleanup_orphaned_reading_progress').execute()
                logger.info("✓ Ran orphaned reading progress cleanup function")
                
            except Exception as verification_error:
                logger.warning(f"⚠ Verification step failed: {verification_error}")
                # Don't fail the operation for verification issues
            
            logger.info(f"✓ Successfully deleted PDF {file_id} for user {user_id}")
            logger.info(f"Deletion summary: {deletion_summary}")
            
            return {
                'success': True, 
                'deleted_file': pdf_metadata['filename'],
                'deletion_summary': deletion_summary
            }
            
        except Exception as e:
            logger.error(f"Error deleting user PDF: {e}")
            return {'error': str(e)}, 500

    def get_reading_progress(self, user_id: str, pdf_id: str):
        """Get reading progress for a specific PDF"""
        try:
            progress = self.supabase_admin.table('reading_progress').select('*').eq('user_id', user_id).eq('pdf_id', pdf_id).execute()
            return {'success': True, 'progress': progress.data[0] if progress.data else None}
        except Exception as e:
            logger.error(f"Error getting reading progress: {e}")
            return {'error': str(e)}, 500

    def update_reading_progress(self, user_id: str, pdf_id: str, current_page: int, current_word_index: int, total_words: int):
        """Update reading progress for a PDF"""
        try:
            progress_data = {
                'user_id': user_id,
                'pdf_id': pdf_id,
                'current_page': current_page,
                'current_word_index': current_word_index,
                'total_words': total_words,
                'updated_at': datetime.utcnow().isoformat()
            }
            
            # Use upsert with on_conflict to handle duplicates
            response = self.supabase_admin.table('reading_progress').upsert(
                progress_data, 
                on_conflict='user_id,pdf_id'
            ).execute()
            return {'success': True, 'progress': response.data[0]}
        except Exception as e:
            logger.error(f"Error updating reading progress: {e}")
            return {'error': str(e)}, 500

    # --- BACKGROUND MUSIC METHODS --- #

    def _save_background_music_to_local_storage(self, user_id: str, filename: str, file_data: bytes):
        """Save background music file to local storage"""
        try:
            user_music_storage_path = self._get_user_music_storage_path(user_id)
            
            # Generate unique filename to avoid conflicts
            file_id = str(uuid.uuid4())
            file_extension = os.path.splitext(filename)[1]
            local_filename = f"{file_id}{file_extension}"
            file_path = os.path.join(user_music_storage_path, local_filename)
            
            # Write file to disk
            with open(file_path, 'wb') as f:
                f.write(file_data)
            
            return {
                'file_id': file_id,
                'local_filename': local_filename,
                'file_path': file_path
            }
        except Exception as e:
            logger.error(f"Error saving background music to local storage: {e}")
            raise

    def _get_background_music_from_local_storage(self, user_id: str, file_id: str, filename: str):
        """Get background music file from local storage"""
        try:
            user_music_storage_path = self._get_user_music_storage_path(user_id)
            file_path = os.path.join(user_music_storage_path, filename)
            
            if os.path.exists(file_path):
                with open(file_path, 'rb') as f:
                    return f.read()
            else:
                return None
        except Exception as e:
            logger.error(f"Error getting background music from local storage: {e}")
            return None

    def _delete_background_music_from_local_storage(self, user_id: str, filename: str):
        """Delete background music file from local storage"""
        try:
            user_music_storage_path = self._get_user_music_storage_path(user_id)
            file_path = os.path.join(user_music_storage_path, filename)
            
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting background music from local storage: {e}")
            return False

    def get_user_background_music(self, user_id: str):
        """Get list of user's background music files"""
        try:
            if not self.supabase:
                return {'error': 'Authentication service not configured'}, 500
            
            # Get background music files from database
            music_records = self.supabase_admin.table('user_background_music').select('*').eq('user_id', user_id).order('created_at', desc=True).execute()
            
            return {
                'success': True,
                'music_files': music_records.data
            }
        except Exception as e:
            logger.error(f"Error getting user background music: {e}")
            return {'error': str(e)}, 500

    def save_background_music(self, user_id: str, filename: str, file_data: bytes):
        """Save background music file and metadata"""
        try:
            if not self.supabase:
                return {'error': 'Authentication service not configured'}, 500
            
            # Save file to local storage
            storage_result = self._save_background_music_to_local_storage(user_id, filename, file_data)
            
            # Get file type from extension
            file_extension = os.path.splitext(filename)[1].lower()
            file_type = file_extension[1:] if file_extension else 'unknown'
            
            # Insert metadata into database
            music_metadata = {
                'user_id': user_id,
                'filename': filename,
                'file_id': storage_result['file_id'],
                'local_filename': storage_result['local_filename'],
                'file_size': len(file_data),
                'file_type': file_type
            }
            
            result = self.supabase_admin.table('user_background_music').insert(music_metadata).execute()
            
            return {
                'success': True,
                'file_id': storage_result['file_id'],
                'filename': filename,
                'file_size': len(file_data)
            }
            
        except Exception as e:
            logger.error(f"Error saving background music: {e}")
            return {'error': str(e)}, 500

    def get_background_music_file(self, user_id: str, file_id: str):
        """Get background music file content from local storage"""
        try:
            if not self.supabase:
                return {'error': 'Authentication service not configured'}, 500
            
            # Get music metadata from database
            music_record = self.supabase_admin.table('user_background_music').select('*').eq('user_id', user_id).eq('file_id', file_id).execute()
            
            if not music_record.data:
                return {'error': 'Background music not found'}, 404
            
            music_metadata = music_record.data[0]
            
            # Get file content from local storage
            file_data = self._get_background_music_from_local_storage(user_id, file_id, music_metadata['local_filename'])
            
            if file_data is None:
                return {'error': 'Background music file not found in storage'}, 404
            
            return {
                'success': True,
                'file_data': file_data,
                'metadata': music_metadata
            }
        except Exception as e:
            logger.error(f"Error getting background music file: {e}")
            return {'error': str(e)}, 500

    def delete_background_music(self, user_id: str, file_id: str):
        """Delete background music file and metadata"""
        try:
            if not self.supabase:
                return {'error': 'Authentication service not configured'}, 500
            
            # Get music metadata
            music_record = self.supabase_admin.table('user_background_music').select('*').eq('user_id', user_id).eq('file_id', file_id).execute()
            
            if not music_record.data:
                return {'error': 'Background music not found'}, 404
            
            music_metadata = music_record.data[0]
            logger.info(f"Starting deletion of background music: {music_metadata['filename']} (ID: {file_id}) for user {user_id}")
            
            # Delete from local storage first
            try:
                if self._delete_background_music_from_local_storage(user_id, music_metadata['local_filename']):
                    logger.info(f"✓ Deleted local music file: {music_metadata['local_filename']}")
                else:
                    logger.warning(f"⚠ Local music file not found: {music_metadata['local_filename']}")
            except Exception as storage_error:
                logger.warning(f"⚠ Failed to delete local music file: {storage_error}")
                # Continue with database cleanup even if file deletion fails
            
            # Delete metadata from database
            try:
                delete_result = self.supabase_admin.table('user_background_music').delete().eq('user_id', user_id).eq('file_id', file_id).execute()
                music_records_deleted = len(delete_result.data) if delete_result.data else 0
                
                if music_records_deleted > 0:
                    logger.info(f"✓ Deleted {music_records_deleted} background music metadata record(s)")
                else:
                    logger.warning(f"⚠ No background music metadata records were deleted for file_id: {file_id}")
                    return {'error': 'No records were deleted'}, 404
                    
            except Exception as db_error:
                logger.error(f"✗ Failed to delete background music metadata: {db_error}")
                return {'error': f'Database deletion failed: {str(db_error)}'}, 500
            
            logger.info(f"✓ Successfully deleted background music {file_id} for user {user_id}")
            
            return {
                'success': True, 
                'deleted_file': music_metadata['filename']
            }
            
        except Exception as e:
            logger.error(f"Error deleting background music: {e}")
            return {'error': str(e)}, 500

    def get_user_preferences(self, user_id: str):
        """Get user's default preferences"""
        try:
            if not self.supabase:
                return {'error': 'Authentication service not configured'}, 500
            
            # Get user preferences from database
            prefs_result = self.supabase_admin.table('user_preferences').select('*').eq('user_id', user_id).execute()
            
            if prefs_result.data:
                prefs = prefs_result.data[0]
                return {
                    'success': True,
                    'preferences': {
                        'voice_model': prefs['voice_model'],
                        'voice_speed': float(prefs['voice_speed']),
                        'skip_patterns': prefs['skip_patterns']
                    }
                }
            else:
                # Create default preferences for the user
                default_prefs = {
                    'user_id': user_id,
                    'voice_model': 'kokoro-af-heart',
                    'voice_speed': 1.0,
                    'skip_patterns': False
                }
                
                insert_result = self.supabase_admin.table('user_preferences').insert(default_prefs).execute()
                
                return {
                    'success': True,
                    'preferences': {
                        'voice_model': default_prefs['voice_model'],
                        'voice_speed': default_prefs['voice_speed'],
                        'skip_patterns': default_prefs['skip_patterns']
                    }
                }
                
        except Exception as e:
            logger.error(f"Error getting user preferences: {e}")
            return {'error': str(e)}, 500

    def update_user_preferences(self, user_id: str, preferences: dict):
        """Update user's default preferences"""
        try:
            if not self.supabase:
                return {'error': 'Authentication service not configured'}, 500
            
            # Validate preferences
            update_data = {}
            if 'voice_model' in preferences:
                update_data['voice_model'] = preferences['voice_model']
            if 'voice_speed' in preferences:
                speed = float(preferences['voice_speed'])
                if speed < 0.1 or speed > 5.0:
                    return {'error': 'Voice speed must be between 0.1 and 5.0'}, 400
                update_data['voice_speed'] = speed
            if 'skip_patterns' in preferences:
                update_data['skip_patterns'] = bool(preferences['skip_patterns'])
            
            if not update_data:
                return {'error': 'No valid preferences provided'}, 400
            
            # Update preferences in database
            result = self.supabase_admin.table('user_preferences').update(update_data).eq('user_id', user_id).execute()
            
            if not result.data:
                # If no rows were updated, create new preferences
                new_prefs = {
                    'user_id': user_id,
                    'voice_model': update_data.get('voice_model', 'kokoro-af-heart'),
                    'voice_speed': update_data.get('voice_speed', 1.0),
                    'skip_patterns': update_data.get('skip_patterns', False)
                }
                result = self.supabase_admin.table('user_preferences').insert(new_prefs).execute()
            
            return {'success': True, 'updated': len(result.data)}
            
        except Exception as e:
            logger.error(f"Error updating user preferences: {e}")
            return {'error': str(e)}, 500

    def get_book_preferences(self, user_id: str, pdf_id: str):
        """Get book-specific preferences"""
        try:
            if not self.supabase:
                return {'error': 'Authentication service not configured'}, 500
            
            # Get book preferences from database
            prefs_result = self.supabase_admin.table('book_preferences').select('*').eq('user_id', user_id).eq('pdf_id', pdf_id).execute()
            
            if prefs_result.data:
                prefs = prefs_result.data[0]
                return {
                    'success': True,
                    'preferences': {
                        'voice_model': prefs['voice_model'],
                        'voice_speed': float(prefs['voice_speed']) if prefs['voice_speed'] is not None else None,
                        'skip_patterns': prefs['skip_patterns'],
                        'background_music_enabled': prefs['background_music_enabled'],
                        'background_music_file_id': prefs['background_music_file_id'],
                        'background_music_volume': float(prefs['background_music_volume']) if prefs['background_music_volume'] is not None else 0.10
                    }
                }
            else:
                return {
                    'success': True,
                    'preferences': None  # No book-specific preferences
                }
                
        except Exception as e:
            logger.error(f"Error getting book preferences: {e}")
            return {'error': str(e)}, 500

    def update_book_preferences(self, user_id: str, pdf_id: str, preferences: dict):
        """Update book-specific preferences"""
        try:
            if not self.supabase:
                return {'error': 'Authentication service not configured'}, 500
            
            # Validate preferences
            update_data = {'user_id': user_id, 'pdf_id': pdf_id}
            
            if 'voice_model' in preferences:
                update_data['voice_model'] = preferences['voice_model']
            if 'voice_speed' in preferences:
                if preferences['voice_speed'] is not None:
                    speed = float(preferences['voice_speed'])
                    if speed < 0.1 or speed > 5.0:
                        return {'error': 'Voice speed must be between 0.1 and 5.0'}, 400
                    update_data['voice_speed'] = speed
                else:
                    update_data['voice_speed'] = None
            if 'skip_patterns' in preferences:
                update_data['skip_patterns'] = bool(preferences['skip_patterns']) if preferences['skip_patterns'] is not None else None
            if 'background_music_enabled' in preferences:
                update_data['background_music_enabled'] = bool(preferences['background_music_enabled'])
            if 'background_music_file_id' in preferences:
                update_data['background_music_file_id'] = preferences['background_music_file_id']
            if 'background_music_volume' in preferences:
                volume = float(preferences['background_music_volume'])
                if volume < 0.0 or volume > 1.0:
                    return {'error': 'Background music volume must be between 0.0 and 1.0'}, 400
                update_data['background_music_volume'] = volume
            
            # Try to update existing record
            result = self.supabase_admin.table('book_preferences').update(update_data).eq('user_id', user_id).eq('pdf_id', pdf_id).execute()
            
            if not result.data:
                # If no rows were updated, create new book preferences
                result = self.supabase_admin.table('book_preferences').insert(update_data).execute()
            
            return {'success': True, 'updated': len(result.data)}
            
        except Exception as e:
            logger.error(f"Error updating book preferences: {e}")
            return {'error': str(e)}, 500

    def delete_book_preferences(self, user_id: str, pdf_id: str):
        """Delete book-specific preferences (revert to user defaults)"""
        try:
            if not self.supabase:
                return {'error': 'Authentication service not configured'}, 500
            
            # Delete book preferences from database
            result = self.supabase_admin.table('book_preferences').delete().eq('user_id', user_id).eq('pdf_id', pdf_id).execute()
            
            return {'success': True, 'deleted': len(result.data)}
            
        except Exception as e:
            logger.error(f"Error deleting book preferences: {e}")
            return {'error': str(e)}, 500

    def get_effective_preferences(self, user_id: str, pdf_id: str):
        """Get effective preferences for a book (combines user defaults with book overrides)"""
        try:
            if not self.supabase:
                return {'error': 'Authentication service not configured'}, 500
            
            # Use the database function to get effective preferences
            result = self.supabase_admin.rpc('get_effective_preferences', {'user_uuid': user_id, 'pdf_file_id': pdf_id}).execute()
            
            if result.data:
                prefs = result.data
                return {
                    'success': True,
                    'preferences': {
                        'voice_model': prefs['voice_model'],
                        'voice_speed': float(prefs['voice_speed']),
                        'skip_patterns': prefs['skip_patterns'],
                        'background_music_enabled': prefs['background_music_enabled'],
                        'background_music_file_id': prefs['background_music_file_id'],
                        'background_music_volume': float(prefs['background_music_volume']),
                        'has_book_overrides': prefs['has_book_overrides']
                    }
                }
            else:
                # Fallback to defaults if function fails
                return {
                    'success': True,
                    'preferences': {
                        'voice_model': 'kokoro-af-heart',
                        'voice_speed': 1.0,
                        'skip_patterns': False,
                        'background_music_enabled': False,
                        'background_music_file_id': None,
                        'background_music_volume': 0.10,
                        'has_book_overrides': False
                    }
                }
                
        except Exception as e:
            logger.error(f"Error getting effective preferences: {e}")
            return {'error': str(e)}, 500

# Global auth service instance
auth_service = AuthService()

def token_required(f):
    """Decorator to require authentication for routes"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        if auth_header:
            try:
                token = auth_header.split(' ')[1]  # Bearer <token>
            except IndexError:
                return jsonify({'error': 'Invalid token format'}), 401
        
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        # Verify token
        result = auth_service.verify_token(token)
        if 'error' in result:
            return jsonify(result), 401
        
        # Add user to request context
        request.current_user = result['user']
        return f(*args, **kwargs)
    
    return decorated 