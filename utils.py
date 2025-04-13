import os
import shutil
import time

def get_file_size_mb(size_in_bytes: int) -> float:
    """
    Convert file size from bytes to megabytes.
    
    Args:
        size_in_bytes: File size in bytes
        
    Returns:
        float: File size in MB
    """
    return size_in_bytes / (1024 * 1024)

def ensure_temp_dir(directory: str = "temp") -> str:
    """
    Ensure that a temporary directory exists.
    
    Args:
        directory: Directory path
        
    Returns:
        str: Path to the directory
    """
    if not os.path.exists(directory):
        os.makedirs(directory)
    return directory

def clean_temp_files(directory: str = "temp") -> None:
    """
    Clean temporary files in a directory.
    
    Args:
        directory: Directory path
    """
    if os.path.exists(directory):
        for file in os.listdir(directory):
            file_path = os.path.join(directory, file)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f"Error deleting {file_path}: {e}")

def format_time(seconds: float) -> str:
    """
    Format time in seconds to a readable string.
    
    Args:
        seconds: Time in seconds
        
    Returns:
        str: Formatted time string
    """
    if seconds < 60:
        return f"{seconds:.1f} seconds"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        sec = seconds % 60
        return f"{minutes} min {sec:.0f} sec"
    else:
        hours = int(seconds / 3600)
        minutes = int((seconds % 3600) / 60)
        return f"{hours} hr {minutes} min"

def timestamp() -> int:
    """
    Get current timestamp.
    
    Returns:
        int: Current timestamp
    """
    return int(time.time())
