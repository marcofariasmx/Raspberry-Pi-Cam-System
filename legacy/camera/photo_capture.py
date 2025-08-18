"""
High-Resolution Photo Capture

Handles still photo capture without interrupting video streaming,
including file management, metadata, and directory organization.
"""

import os
import time
from datetime import datetime
from typing import Tuple, Optional
from src.config import AppConfig
from .camera_exceptions import PhotoCaptureError, handle_camera_error

# Import picamera2 - graceful handling for development environments
try:
    from picamera2 import Picamera2 # type: ignore
    PICAMERA2_AVAILABLE = True
except ImportError:
    PICAMERA2_AVAILABLE = False
    # Mock for development
    class Picamera2:
        def capture_request(self): return MockRequest()
    
    class MockRequest:
        def save(self, stream, filename): pass
        def release(self): pass


class PhotoCapture:
    """
    Manages high-resolution photo capture operations
    
    Handles photo capture from the main (full resolution) stream while
    maintaining video streaming from the lores stream simultaneously.
    """
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.photos_captured: int = 0
        self.last_capture_time: Optional[float] = None
    
    @handle_camera_error
    def capture_photo(self, camera_device: Picamera2) -> Tuple[bool, str, str]:
        """
        Capture high-resolution still photo without interrupting video stream
        
        Args:
            camera_device: Active Picamera2 instance
            
        Returns:
            Tuple[bool, str, str]: (success, message, filename)
            
        Raises:
            PhotoCaptureError: If capture fails
        """
        if not camera_device:
            raise PhotoCaptureError("No camera device available")
        
        if not PICAMERA2_AVAILABLE:
            # For development/testing environments
            return self._simulate_photo_capture()
        
        try:
            print("📸 Capturing high-resolution photo...")
            
            # Ensure photos directory exists
            self._ensure_photos_directory()
            
            # Generate filename with timestamp
            filename = self._generate_filename()
            filepath = self._get_full_filepath(filename)
            
            # Capture from main stream (full resolution) while lores continues streaming
            request = camera_device.capture_request()
            try:
                request.save("main", filepath)
                print(f"✅ Photo saved: {filename}")
                
                # Update capture statistics
                self.photos_captured += 1
                self.last_capture_time = time.time()
                
                return True, "Photo captured successfully", filename
                
            finally:
                # Critical: release the request to free memory
                request.release()
            
        except Exception as e:
            print(f"❌ Photo capture failed: {e}")
            raise PhotoCaptureError(f"Capture failed: {str(e)}")
    
    def _simulate_photo_capture(self) -> Tuple[bool, str, str]:
        """Simulate photo capture for development environments"""
        print("📸 Simulating photo capture (development mode)...")
        
        self._ensure_photos_directory()
        filename = self._generate_filename()
        filepath = self._get_full_filepath(filename)
        
        # Create a dummy file for testing
        with open(filepath, 'w') as f:
            f.write(f"Simulated photo captured at {datetime.now().isoformat()}")
        
        self.photos_captured += 1
        self.last_capture_time = time.time()
        
        print(f"✅ Simulated photo saved: {filename}")
        return True, "Photo captured successfully (simulated)", filename
    
    def _ensure_photos_directory(self):
        """Ensure the photos directory exists"""
        try:
            os.makedirs(self.config.photos_dir, exist_ok=True)
        except Exception as e:
            raise PhotoCaptureError(f"Failed to create photos directory: {str(e)}")
    
    def _generate_filename(self) -> str:
        """
        Generate a unique filename with timestamp
        
        Returns:
            str: Filename in format 'photo_YYYYMMDD_HHMMSS.jpg'
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"photo_{timestamp}.jpg"
    
    def _get_full_filepath(self, filename: str) -> str:
        """
        Get the full file path for a given filename
        
        Args:
            filename: The photo filename
            
        Returns:
            str: Full path to the photo file
        """
        return os.path.join(self.config.photos_dir, filename)
    
    def get_photo_info(self, filename: str) -> Optional[dict]:
        """
        Get information about a captured photo
        
        Args:
            filename: The photo filename
            
        Returns:
            dict: Photo information or None if file doesn't exist
        """
        filepath = self._get_full_filepath(filename)
        
        if not os.path.exists(filepath):
            return None
        
        try:
            stat = os.stat(filepath)
            return {
                "filename": filename,
                "filepath": filepath,
                "size": stat.st_size,
                "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "size_mb": round(stat.st_size / (1024 * 1024), 2)
            }
        except Exception as e:
            print(f"⚠️  Error getting photo info for {filename}: {e}")
            return None
    
    def list_photos(self) -> list:
        """
        List all captured photos with metadata
        
        Returns:
            list: List of photo information dictionaries
        """
        photos = []
        
        if not os.path.exists(self.config.photos_dir):
            return photos
        
        try:
            for filename in os.listdir(self.config.photos_dir):
                if self._is_photo_file(filename):
                    photo_info = self.get_photo_info(filename)
                    if photo_info:
                        photos.append(photo_info)
            
            # Sort by creation time (newest first)
            photos.sort(key=lambda x: x["created"], reverse=True)
            
            # Apply max photos limit if configured
            if self.config.max_photos > 0:
                photos = photos[:self.config.max_photos]
            
            return photos
            
        except Exception as e:
            print(f"⚠️  Error listing photos: {e}")
            return []
    
    def delete_photo(self, filename: str) -> Tuple[bool, str]:
        """
        Delete a specific photo
        
        Args:
            filename: Name of the photo file to delete
            
        Returns:
            Tuple[bool, str]: (success, message)
        """
        # Security check - validate filename
        if not self._is_valid_filename(filename):
            return False, "Invalid filename"
        
        filepath = self._get_full_filepath(filename)
        
        if not os.path.exists(filepath):
            return False, "Photo not found"
        
        try:
            os.remove(filepath)
            print(f"🗑️  Photo deleted: {filename}")
            return True, f"Photo {filename} deleted successfully"
            
        except Exception as e:
            error_msg = f"Failed to delete photo: {str(e)}"
            print(f"❌ {error_msg}")
            return False, error_msg
    
    def cleanup_old_photos(self) -> Tuple[int, int]:
        """
        Clean up old photos if max_photos limit is exceeded
        
        Returns:
            Tuple[int, int]: (photos_deleted, photos_remaining)
        """
        if self.config.max_photos <= 0:
            return 0, len(self.list_photos())
        
        photos = self.list_photos()
        photos_to_delete = len(photos) - self.config.max_photos
        
        if photos_to_delete <= 0:
            return 0, len(photos)
        
        deleted_count = 0
        
        # Delete oldest photos (photos are sorted newest first)
        for photo in photos[-photos_to_delete:]:
            success, _ = self.delete_photo(photo["filename"])
            if success:
                deleted_count += 1
        
        remaining_photos = len(photos) - deleted_count
        
        if deleted_count > 0:
            print(f"🧹 Cleaned up {deleted_count} old photos, {remaining_photos} remaining")
        
        return deleted_count, remaining_photos
    
    def get_capture_stats(self) -> dict:
        """
        Get photo capture statistics
        
        Returns:
            dict: Capture statistics
        """
        photos_list = self.list_photos()
        total_size = sum(photo["size"] for photo in photos_list)
        
        return {
            "photos_captured": self.photos_captured,
            "photos_stored": len(photos_list),
            "last_capture_time": self.last_capture_time,
            "total_storage_bytes": total_size,
            "total_storage_mb": round(total_size / (1024 * 1024), 2),
            "photos_directory": self.config.photos_dir,
            "max_photos_limit": self.config.max_photos
        }
    
    def _is_photo_file(self, filename: str) -> bool:
        """Check if filename is a valid photo file"""
        return filename.lower().endswith(('.jpg', '.jpeg', '.png'))
    
    def _is_valid_filename(self, filename: str) -> bool:
        """Validate filename for security (prevent directory traversal)"""
        if not filename:
            return False
        
        # Prevent directory traversal attacks
        if '..' in filename or '/' in filename or '\\' in filename:
            return False
        
        # Must be a photo file
        if not self._is_photo_file(filename):
            return False
        
        return True


def get_photos_directory_size(photos_dir: str) -> Tuple[int, float]:
    """
    Get the total size of the photos directory
    
    Args:
        photos_dir: Path to photos directory
        
    Returns:
        Tuple[int, float]: (total_bytes, total_mb)
    """
    if not os.path.exists(photos_dir):
        return 0, 0.0
    
    total_size = 0
    
    try:
        for filename in os.listdir(photos_dir):
            filepath = os.path.join(photos_dir, filename)
            if os.path.isfile(filepath):
                total_size += os.path.getsize(filepath)
    except Exception as e:
        print(f"⚠️  Error calculating directory size: {e}")
    
    return total_size, round(total_size / (1024 * 1024), 2)


def validate_photos_directory(photos_dir: str) -> bool:
    """
    Validate that the photos directory is accessible and writable
    
    Args:
        photos_dir: Path to photos directory
        
    Returns:
        bool: True if directory is valid and writable
    """
    try:
        # Create directory if it doesn't exist
        os.makedirs(photos_dir, exist_ok=True)
        
        # Test write access
        test_file = os.path.join(photos_dir, ".write_test")
        with open(test_file, 'w') as f:
            f.write("test")
        
        # Clean up test file
        os.remove(test_file)
        
        return True
        
    except Exception as e:
        print(f"⚠️  Photos directory validation failed: {e}")
        return False
