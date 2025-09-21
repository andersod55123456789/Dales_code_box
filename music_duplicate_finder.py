import os
import hashlib
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
import threading
from collections import defaultdict
import time

# Try to import mutagen for metadata reading
try:
    from mutagen import File as MutagenFile
    from mutagen.id3 import ID3NoHeaderError
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False
    print("Mutagen not installed. Metadata features will be disabled.")
    print("To install: pip install mutagen")

class MusicDuplicateFinder:
    def __init__(self, root):
        self.root = root
        self.root.title("Music Duplicate Finder")
        self.root.geometry("1400x900")
        
        # Default folder path
        self.folder_path = r"C:\Users\DBA\Desktop\CASSIETRANSFER\Music"
        
        # Data storage
        self.duplicates = []
        self.current_duplicate_index = 0
        
        # Audio file extensions
        self.audio_extensions = {'.mp3', '.flac', '.wav', '.m4a', '.aac', '.ogg', '.wma', '.mp4'}
        
        self.setup_ui()
        
    def setup_ui(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # Folder selection
        ttk.Label(main_frame, text="Music Folder:").grid(row=0, column=0, sticky=tk.W, pady=5)
        
        folder_frame = ttk.Frame(main_frame)
        folder_frame.grid(row=0, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        folder_frame.columnconfigure(0, weight=1)
        
        self.folder_var = tk.StringVar(value=self.folder_path)
        folder_entry = ttk.Entry(folder_frame, textvariable=self.folder_var, width=50)
        folder_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 5))
        
        browse_btn = ttk.Button(folder_frame, text="Browse", command=self.browse_folder)
        browse_btn.grid(row=0, column=1)
        
        # Scan button
        self.scan_btn = ttk.Button(main_frame, text="Scan for Duplicates", command=self.start_scan)
        self.scan_btn.grid(row=1, column=0, columnspan=3, pady=10)
        
        # Progress bar
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        
        # Status label
        self.status_var = tk.StringVar(value="Ready to scan")
        status_label = ttk.Label(main_frame, textvariable=self.status_var)
        status_label.grid(row=3, column=0, columnspan=3, pady=5)
        
        # Results frame
        results_frame = ttk.LabelFrame(main_frame, text="Duplicate Files", padding="10")
        results_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(1, weight=1)
        main_frame.rowconfigure(4, weight=1)
        
        # Navigation frame
        nav_frame = ttk.Frame(results_frame)
        nav_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        nav_frame.columnconfigure(1, weight=1)
        
        self.prev_btn = ttk.Button(nav_frame, text="← Previous", command=self.prev_duplicate, state='disabled')
        self.prev_btn.grid(row=0, column=0, padx=(0, 5))
        
        self.duplicate_info = tk.StringVar(value="No duplicates found")
        info_label = ttk.Label(nav_frame, textvariable=self.duplicate_info)
        info_label.grid(row=0, column=1, padx=5)
        
        self.next_btn = ttk.Button(nav_frame, text="Next →", command=self.next_duplicate, state='disabled')
        self.next_btn.grid(row=0, column=2, padx=(5, 0))
        
        # Files comparison frame
        compare_frame = ttk.Frame(results_frame)
        compare_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        compare_frame.columnconfigure(0, weight=1)
        compare_frame.columnconfigure(2, weight=1)
        compare_frame.rowconfigure(0, weight=1)
        
        # Left file panel
        left_frame = ttk.LabelFrame(compare_frame, text="File 1", padding="10")
        left_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(0, weight=1)
        
        self.left_text = tk.Text(left_frame, wrap=tk.WORD, height=20, width=45, font=('Consolas', 9))
        left_scrollbar = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.left_text.yview)
        self.left_text.configure(yscrollcommand=left_scrollbar.set)
        self.left_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        left_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # Action buttons frame
        action_frame = ttk.Frame(compare_frame)
        action_frame.grid(row=0, column=1, padx=10, pady=50)
        
        ttk.Button(action_frame, text="Keep File 1\nDelete File 2", 
                  command=self.keep_left).pack(pady=5, fill=tk.X)
        ttk.Button(action_frame, text="Keep File 2\nDelete File 1", 
                  command=self.keep_right).pack(pady=5, fill=tk.X)
        ttk.Button(action_frame, text="Keep Both Files", 
                  command=self.keep_both).pack(pady=5, fill=tk.X)
        ttk.Button(action_frame, text="Skip This Pair", 
                  command=self.skip_pair).pack(pady=5, fill=tk.X)
        
        # Right file panel
        right_frame = ttk.LabelFrame(compare_frame, text="File 2", padding="10")
        right_frame.grid(row=0, column=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(5, 0))
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(0, weight=1)
        
        self.right_text = tk.Text(right_frame, wrap=tk.WORD, height=15, width=40)
        right_scrollbar = ttk.Scrollbar(right_frame, orient=tk.VERTICAL, command=self.right_text.yview)
        self.right_text.configure(yscrollcommand=right_scrollbar.set)
        self.right_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        right_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
    def browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.folder_path)
        if folder:
            self.folder_var.set(folder)
            self.folder_path = folder
    
    def start_scan(self):
        self.folder_path = self.folder_var.get()
        if not os.path.exists(self.folder_path):
            messagebox.showerror("Error", "Selected folder does not exist!")
            return
        
        self.scan_btn.config(state='disabled')
        self.progress.start()
        self.status_var.set("Scanning for duplicates...")
        
        # Start scanning in a separate thread
        thread = threading.Thread(target=self.scan_for_duplicates)
        thread.daemon = True
        thread.start()
    
    def scan_for_duplicates(self):
        try:
            # Find all audio files
            audio_files = []
            for root, dirs, files in os.walk(self.folder_path):
                for file in files:
                    if Path(file).suffix.lower() in self.audio_extensions:
                        audio_files.append(os.path.join(root, file))
            
            self.root.after(0, lambda: self.status_var.set(f"Found {len(audio_files)} audio files. Analyzing..."))
            
            # Group files by potential duplicates
            duplicates_by_hash = defaultdict(list)
            duplicates_by_name = defaultdict(list)
            duplicates_by_size = defaultdict(list)
            
            total_files = len(audio_files)
            for i, file_path in enumerate(audio_files):
                try:
                    # Update progress
                    if i % 10 == 0:
                        self.root.after(0, lambda i=i: self.status_var.set(
                            f"Processing file {i+1}/{total_files}..."))
                    
                    # Get file info
                    file_stat = os.stat(file_path)
                    file_size = file_stat.st_size
                    file_name = os.path.basename(file_path).lower()
                    
                    # Group by size (quick check)
                    duplicates_by_size[file_size].append(file_path)
                    
                    # Group by similar names (without extension)
                    name_without_ext = os.path.splitext(file_name)[0]
                    # Clean the name for comparison
                    clean_name = ''.join(c for c in name_without_ext if c.isalnum()).lower()
                    duplicates_by_name[clean_name].append(file_path)
                    
                    # Group by metadata if available
                    if MUTAGEN_AVAILABLE:
                        metadata = self.get_music_metadata(file_path)
                        if metadata:
                            # Create a metadata signature for comparison
                            title = metadata.get('Title', '').lower().strip()
                            artist = metadata.get('Artist', '').lower().strip()
                            album = metadata.get('Album', '').lower().strip()
                            
                            if title and artist:
                                metadata_key = f"{artist}_{title}".replace(' ', '_')
                                metadata_key = ''.join(c for c in metadata_key if c.isalnum() or c == '_')
                                if metadata_key not in duplicates_by_name:
                                    duplicates_by_name[metadata_key] = []
                                duplicates_by_name[metadata_key].append(file_path)
                    
                    # For files with same size, calculate hash
                    if file_size > 0:  # Avoid empty files
                        file_hash = self.calculate_file_hash(file_path)
                        if file_hash:
                            duplicates_by_hash[file_hash].append(file_path)
                    
                except (OSError, IOError) as e:
                    print(f"Error processing {file_path}: {e}")
                    continue
            
            # Find actual duplicates
            self.duplicates = []
            
            # Hash-based duplicates (most reliable)
            for file_hash, files in duplicates_by_hash.items():
                if len(files) > 1:
                    for i in range(len(files)):
                        for j in range(i + 1, len(files)):
                            self.duplicates.append({
                                'type': 'Identical Content',
                                'file1': files[i],
                                'file2': files[j],
                                'reason': 'Files have identical content (same hash)'
                            })
            
            # Size-based duplicates (same size, different hash - potential duplicates)
            for size, files in duplicates_by_size.items():
                if len(files) > 1 and size > 1024:  # Only check files > 1KB
                    for i in range(len(files)):
                        for j in range(i + 1, len(files)):
                            # Check if not already added as hash duplicate
                            already_added = any(
                                (d['file1'] == files[i] and d['file2'] == files[j]) or
                                (d['file1'] == files[j] and d['file2'] == files[i])
                                for d in self.duplicates
                            )
                            if not already_added:
                                self.duplicates.append({
                                    'type': 'Same Size',
                                    'file1': files[i],
                                    'file2': files[j],
                                    'reason': f'Files have identical size ({size} bytes)'
                                })
            
            # Name-based duplicates
            for clean_name, files in duplicates_by_name.items():
                if len(files) > 1:
                    for i in range(len(files)):
                        for j in range(i + 1, len(files)):
                            # Check if not already added
                            already_added = any(
                                (d['file1'] == files[i] and d['file2'] == files[j]) or
                                (d['file1'] == files[j] and d['file2'] == files[i])
                                for d in self.duplicates
                            )
                            if not already_added:
                                self.duplicates.append({
                                    'type': 'Similar Name',
                                    'file1': files[i],
                                    'file2': files[j],
                                    'reason': f'Files have similar names: "{clean_name}"'
                                })
            
            # Update UI in main thread
            self.root.after(0, self.scan_completed)
            
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", f"Error during scan: {e}"))
            self.root.after(0, self.scan_completed)
    
    def calculate_file_hash(self, file_path, chunk_size=8192):
        """Calculate MD5 hash of file"""
        try:
            hash_md5 = hashlib.md5()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(chunk_size), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except (IOError, OSError):
            return None
    
    def scan_completed(self):
        self.progress.stop()
        self.scan_btn.config(state='normal')
        
        if self.duplicates:
            self.status_var.set(f"Found {len(self.duplicates)} potential duplicate pairs")
            self.current_duplicate_index = 0
            self.show_current_duplicate()
            self.next_btn.config(state='normal' if len(self.duplicates) > 1 else 'disabled')
            self.prev_btn.config(state='disabled')
        else:
            self.status_var.set("No duplicates found")
            self.duplicate_info.set("No duplicates found")
            self.clear_file_displays()
    
    def show_current_duplicate(self):
        if not self.duplicates or self.current_duplicate_index >= len(self.duplicates):
            return
        
        duplicate = self.duplicates[self.current_duplicate_index]
        self.duplicate_info.set(f"Duplicate {self.current_duplicate_index + 1} of {len(self.duplicates)} ({duplicate['type']})")
        
        # Display file 1 info
        self.left_text.delete(1.0, tk.END)
        file1_info = self.get_file_info(duplicate['file1'])
        self.left_text.insert(tk.END, file1_info)
        
        # Display file 2 info
        self.right_text.delete(1.0, tk.END)
        file2_info = self.get_file_info(duplicate['file2'])
        self.right_text.insert(tk.END, file2_info)
    
    def get_file_info(self, file_path):
        try:
            stat = os.stat(file_path)
            size_mb = stat.st_size / (1024 * 1024)
            mod_time = time.ctime(stat.st_mtime)
            
            info = f"Path: {file_path}\n\n"
            info += f"Filename: {os.path.basename(file_path)}\n"
            info += f"Size: {size_mb:.2f} MB\n"
            info += f"Modified: {mod_time}\n"
            info += f"Directory: {os.path.dirname(file_path)}\n\n"
            
            # Add metadata if available
            metadata = self.get_music_metadata(file_path)
            if metadata:
                info += "=== MUSIC METADATA ===\n"
                for key, value in metadata.items():
                    if value:  # Only show non-empty values
                        info += f"{key}: {value}\n"
                info += "\n"
            
            # Add technical info
            tech_info = self.get_technical_info(file_path)
            if tech_info:
                info += "=== TECHNICAL INFO ===\n"
                for key, value in tech_info.items():
                    if value:
                        info += f"{key}: {value}\n"
            
            return info
        except Exception as e:
            return f"Error reading file info: {e}"
    
    def get_music_metadata(self, file_path):
        """Extract music metadata using mutagen"""
        if not MUTAGEN_AVAILABLE:
            return {}
        
        try:
            audio_file = MutagenFile(file_path)
            if audio_file is None:
                return {}
            
            metadata = {}
            
            # Common metadata fields with various possible tag names
            tag_mappings = {
                'Title': ['TIT2', 'TITLE', '\xa9nam', 'title'],
                'Artist': ['TPE1', 'ARTIST', '\xa9ART', 'artist', 'albumartist'],
                'Album': ['TALB', 'ALBUM', '\xa9alb', 'album'],
                'Album Artist': ['TPE2', 'ALBUMARTIST', 'aART', 'albumartist'],
                'Date/Year': ['TDRC', 'DATE', 'YEAR', '\xa9day', 'date', 'year'],
                'Genre': ['TCON', 'GENRE', '\xa9gen', 'genre'],
                'Track Number': ['TRCK', 'TRACKNUMBER', 'trkn', 'tracknumber'],
                'Disc Number': ['TPOS', 'DISCNUMBER', 'disk', 'discnumber'],
                'Comment': ['COMM::eng', 'COMMENT', '\xa9cmt', 'comment'],
                'Composer': ['TCOM', 'COMPOSER', '\xa9wrt', 'composer'],
                'Encoder': ['TSSE', 'ENCODER', '\xa9too', 'encoder'],
            }
            
            # Extract metadata
            for display_name, possible_tags in tag_mappings.items():
                value = None
                for tag in possible_tags:
                    if tag in audio_file:
                        tag_value = audio_file[tag]
                        if isinstance(tag_value, list) and tag_value:
                            value = str(tag_value[0])
                        elif tag_value:
                            value = str(tag_value)
                        
                        # Clean up the value
                        if value:
                            value = value.strip()
                            # Handle track numbers (e.g., "1/10" -> "1")
                            if display_name == 'Track Number' and '/' in value:
                                value = f"{value.split('/')[0]} of {value.split('/')[1]}"
                            break
                
                if value:
                    metadata[display_name] = value
            
            return metadata
            
        except Exception as e:
            return {'Metadata Error': str(e)}
    
    def get_technical_info(self, file_path):
        """Extract technical audio information"""
        if not MUTAGEN_AVAILABLE:
            return {}
        
        try:
            audio_file = MutagenFile(file_path)
            if audio_file is None or not hasattr(audio_file, 'info'):
                return {}
            
            info = audio_file.info
            tech_info = {}
            
            # Duration
            if hasattr(info, 'length') and info.length:
                minutes = int(info.length // 60)
                seconds = int(info.length % 60)
                tech_info['Duration'] = f"{minutes}:{seconds:02d}"
            
            # Bitrate
            if hasattr(info, 'bitrate') and info.bitrate:
                tech_info['Bitrate'] = f"{info.bitrate} bps"
            
            # Sample Rate
            if hasattr(info, 'sample_rate') and info.sample_rate:
                tech_info['Sample Rate'] = f"{info.sample_rate} Hz"
            
            # Channels
            if hasattr(info, 'channels') and info.channels:
                channels_desc = {1: 'Mono', 2: 'Stereo'}.get(info.channels, f'{info.channels} channels')
                tech_info['Channels'] = channels_desc
            
            # File format specific info
            if hasattr(info, 'mime'):
                tech_info['MIME Type'] = ' '.join(info.mime)
            
            # Codec info
            codec_info = []
            if hasattr(info, 'version') and info.version:
                codec_info.append(f"Version {info.version}")
            if hasattr(info, 'layer') and info.layer:
                codec_info.append(f"Layer {info.layer}")
            if hasattr(info, 'mode') and info.mode:
                codec_info.append(str(info.mode))
            
            if codec_info:
                tech_info['Codec Info'] = ', '.join(codec_info)
            
            return tech_info
            
        except Exception as e:
            return {'Technical Info Error': str(e)}
    
    def clear_file_displays(self):
        self.left_text.delete(1.0, tk.END)
        self.right_text.delete(1.0, tk.END)
    
    def prev_duplicate(self):
        if self.current_duplicate_index > 0:
            self.current_duplicate_index -= 1
            self.show_current_duplicate()
            self.update_navigation_buttons()
    
    def next_duplicate(self):
        if self.current_duplicate_index < len(self.duplicates) - 1:
            self.current_duplicate_index += 1
            self.show_current_duplicate()
            self.update_navigation_buttons()
    
    def update_navigation_buttons(self):
        self.prev_btn.config(state='normal' if self.current_duplicate_index > 0 else 'disabled')
        self.next_btn.config(state='normal' if self.current_duplicate_index < len(self.duplicates) - 1 else 'disabled')
    
    def keep_left(self):
        self.delete_file_and_continue('file2')
    
    def keep_right(self):
        self.delete_file_and_continue('file1')
    
    def keep_both(self):
        messagebox.showinfo("Keep Both", "Both files will be kept. Moving to next duplicate pair.")
        self.move_to_next_duplicate()
    
    def skip_pair(self):
        self.move_to_next_duplicate()
    
    def delete_file_and_continue(self, file_to_delete):
        if not self.duplicates:
            return
            
        duplicate = self.duplicates[self.current_duplicate_index]
        file_path = duplicate[file_to_delete]
        
        # Confirm deletion
        filename = os.path.basename(file_path)
        if messagebox.askyesno("Confirm Deletion", f"Are you sure you want to delete:\n{filename}?"):
            try:
                os.remove(file_path)
                messagebox.showinfo("Success", f"File deleted: {filename}")
                self.move_to_next_duplicate()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete file:\n{e}")
    
    def move_to_next_duplicate(self):
        # Remove current duplicate from list
        if self.duplicates and self.current_duplicate_index < len(self.duplicates):
            self.duplicates.pop(self.current_duplicate_index)
        
        # Adjust index if needed
        if self.current_duplicate_index >= len(self.duplicates):
            self.current_duplicate_index = len(self.duplicates) - 1
        
        # Update display
        if self.duplicates:
            self.show_current_duplicate()
            self.update_navigation_buttons()
        else:
            self.status_var.set("All duplicates processed!")
            self.duplicate_info.set("All duplicates processed!")
            self.clear_file_displays()
            self.prev_btn.config(state='disabled')
            self.next_btn.config(state='disabled')

def main():
    root = tk.Tk()
    app = MusicDuplicateFinder(root)
    root.mainloop()

if __name__ == "__main__":
    main()