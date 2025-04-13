import threading
from typing import Dict, Tuple, Any, Optional

class QueueManager:
    """Manages the queue of video compression tasks."""
    
    def __init__(self):
        """Initialize the queue manager."""
        self.queue = []  # List of (user_id, data) tuples
        self.lock = threading.Lock()
    
    def add_to_queue(self, user_id: int, data: Dict[str, Any]) -> None:
        """
        Add a task to the queue.
        
        Args:
            user_id: Telegram user ID
            data: Task data (chat_id, message_id, etc.)
        """
        with self.lock:
            # Check if user already has a task in the queue
            if not any(uid == user_id for uid, _ in self.queue):
                self.queue.append((user_id, data))
    
    def get_current_task(self) -> Tuple[Optional[int], Optional[Dict[str, Any]]]:
        """
        Get the current task at the front of the queue.
        
        Returns:
            Tuple of (user_id, data) or (None, None) if queue is empty
        """
        with self.lock:
            if not self.queue:
                return None, None
            return self.queue[0]
    
    def task_complete(self, user_id: int) -> bool:
        """
        Mark a task as complete and remove it from the queue.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            bool: True if task was removed, False otherwise
        """
        with self.lock:
            for i, (uid, _) in enumerate(self.queue):
                if uid == user_id:
                    self.queue.pop(i)
                    return True
            return False
    
    def remove_from_queue(self, user_id: int) -> bool:
        """
        Remove a user's task from the queue.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            bool: True if task was removed, False otherwise
        """
        return self.task_complete(user_id)
    
    def get_position(self, user_id: int) -> Optional[int]:
        """
        Get the position of a user's task in the queue.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            int: Position in queue (0-based), or None if not in queue
        """
        with self.lock:
            for i, (uid, _) in enumerate(self.queue):
                if uid == user_id:
                    return i
            return None
    
    def is_in_queue(self, user_id: int) -> bool:
        """
        Check if a user has a task in the queue.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            bool: True if user has a task in queue, False otherwise
        """
        return self.get_position(user_id) is not None
    
    def is_empty(self) -> bool:
        """
        Check if the queue is empty.
        
        Returns:
            bool: True if queue is empty, False otherwise
        """
        with self.lock:
            return len(self.queue) == 0
    
    def size(self) -> int:
        """
        Get the size of the queue.
        
        Returns:
            int: Number of tasks in queue
        """
        with self.lock:
            return len(self.queue)
