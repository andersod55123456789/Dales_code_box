import os
import hashlib
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
import threading
from collections import defaultdict
import time

# Try to import PIL for image info and preview
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image = None
    ImageTk = None

class ImageDuplicateFinder:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Duplicate Finder")
        self.root.geometry("1600x1000")
        
        # Default folder path
        self.folder_path = r"C:\Users\DBA\Desktop"
        
        # Data storage
        self.duplicates = []
        self.current_duplicate_index = 0
        
        # Image file extensions
        self.image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.ico', '.heic', '.heif'}
        
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
        ttk.Label(main_frame, text="Image Folder:").grid(row=0, column=0, sticky=tk.W, pady=5)
        
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
        results_frame = ttk.LabelFrame(main_frame, text="Duplicate Images", padding="10")
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
        
        # Images comparison frame
        compare_frame = ttk.Frame(results_frame)
        compare_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        compare_frame.columnconfigure(0, weight=1)
        compare_frame.columnconfigure(2, weight=1)
        compare_frame.rowconfigure(0, weight=1)
        
        # Left image panel
        left_frame = ttk.LabelFrame(compare_frame, text="Image 1", padding="10")
        left_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(1, weight=1)
        
        # Image preview
        self.left_image_label = tk.Label(left_frame, text="No image", bg="lightgray", width=30, height=15)
        self.left_image_label.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # Image info text
        self.left_text = tk.Text(left_frame, wrap=tk.WORD, height=15, width=40, font=('Consolas', 9))
        left_scrollbar = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.left_text.yview)
        self.left_text.configure(yscrollcommand=left_scrollbar.set)
        self.left_text.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        left_scrollbar.grid(row=1, column=1, sticky=(tk.N, tk.S))
        
        # Action buttons frame
        action_frame = ttk.Frame(compare_frame)
        action_frame.grid(row=0, column=1, padx=15, pady=100)
        
        ttk.Button(action_frame, text="Keep Image 1\nDelete Image 2", 
                  command=self.keep_left).pack(pady=8, fill=tk.X)
        ttk.Button(action_frame, text="Keep Image 2\nDelete Image 1", 
                  command=self.keep_right).pack(pady=8, fill=tk.X)
        ttk.Button(action_frame, text="Keep Both Images", 
                  command=self.keep_both).pack(pady=8, fill=tk.X)
        ttk.Button(action_frame, text="Skip This Pair", 
                  command=self.skip_pair).pack(pady=8, fill=tk.X)
        
        # Right image panel
        right_frame = ttk.LabelFrame(compare_frame, text="Image 2", padding="10")
        right_frame.grid(row=0, column=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(5, 0))
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(1, weight=1)
        
        # Image preview
        self.right_image_label = tk.Label(right_frame, text="No image", bg="lightgray", width=30, height=15)
        self.right_image_label.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # Image info text
        self.right_text = tk.Text(right_frame, wrap=tk.WORD, height=15, width=40, font=('Consolas', 9))
        right_scrollbar = ttk.Scrollbar(right_frame, orient=tk.VERTICAL, command=self.right_text.yview)
        self.right_text.configure(yscrollcommand=right_scrollbar.set)
        self.right_text.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        right_scrollbar.grid(row=1, column=1, sticky=(tk.N, tk.S))
        
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
        self.status_var.set("Scanning for duplicate images...")
        
        # Start scanning in a separate thread
        thread = threading.Thread(target=self.scan_for_duplicates)
        thread.daemon = True
        thread.start()
    
    def scan_for_duplicates(self):
        try:
            # Find all image files
            image_files = []
            for root, dirs, files in os.walk(self.folder_path):
                for file in files:
                    if Path(file).suffix.lower() in self.image_extensions:
                        image_files.append(os.path.join(root, file))
            
            self.root.after(0, lambda: self.status_var.set(f"Found {len(image_files)} image files. Analyzing..."))
            
            # Initialize
            self.duplicates = []
            self.auto_deleted_count = 0
            
            # First pass: Group by file size (much faster than hashing everything)
            size_groups = defaultdict(list)
            for file_path in image_files:
                try:
                    file_stat = os.stat(file_path)
                    file_size = file_stat.st_size
                    if file_size > 0:  # Skip empty files
                        size_groups[file_size].append(file_path)
                except (OSError, IOError):
                    continue
            
            self.root.after(0, lambda: self.status_var.set("Grouping by size complete. Checking content..."))
            
            # Second pass: For each size group with multiple files, check if they're identical
            processed_pairs = set()
            total_groups = len([g for g in size_groups.values() if len(g) > 1])
            current_group = 0
            
            for file_size, files in size_groups.items():
                if len(files) > 1:
                    current_group += 1
                    if current_group % 5 == 0:
                        self.root.after(0, lambda g=current_group, t=total_groups: self.status_var.set(
                            f"Processing size group {g}/{t}..."))
                    
                    # Calculate hashes for files of the same size
                    hash_groups = defaultdict(list)
                    for file_path in files:
                        try:
                            file_hash = self.calculate_file_hash(file_path)
                            if file_hash:
                                hash_groups[file_hash].append(file_path)
                        except Exception as e:
                            continue
                    
                    # Auto-delete identical files (same size + same hash)
                    for file_hash, identical_files in hash_groups.items():
                        if len(identical_files) > 1:
                            # Sort to have consistent behavior
                            identical_files.sort()
                            files_to_delete = identical_files[1:]  # Keep first, delete rest
                            
                            for file_to_delete in files_to_delete:
                                try:
                                    os.remove(file_to_delete)
                                    self.auto_deleted_count += 1
                                except Exception as e:
                                    print(f"Failed to auto-delete {file_to_delete}: {e}")
            
            # Third pass: Look for visually similar images (same dimensions but different content)
            self.root.after(0, lambda: self.status_var.set("Looking for visually similar images..."))
            
            remaining_files = [f for f in image_files if os.path.exists(f)]
            dimension_groups = defaultdict(list)
            
            for file_path in remaining_files:
                try:
                    dimensions = self.get_image_dimensions(file_path)
                    if dimensions:
                        dimension_groups[dimensions].append(file_path)
                except Exception:
                    continue
            
            # Add dimension-based duplicates to manual review
            for dimensions, files in dimension_groups.items():
                if len(files) > 1:
                    for i in range(len(files)):
                        for j in range(i + 1, len(files)):
                            # Only add if not already processed
                            pair = tuple(sorted([files[i], files[j]]))
                            if pair not in processed_pairs:
                                self.duplicates.append({
                                    'type': 'Same Dimensions',
                                    'file1': files[i],
                                    'file2': files[j],
                                    'reason': f'Images have same dimensions: {dimensions[0]}x{dimensions[1]}'
                                })
                                processed_pairs.add(pair)
            
            # Fourth pass: Look for similar file sizes (within 5% difference)
            self.root.after(0, lambda: self.status_var.set("Looking for similar file sizes..."))
            
            remaining_with_sizes = []
            for file_path in remaining_files:
                try:
                    file_stat = os.stat(file_path)
                    remaining_with_sizes.append((file_path, file_stat.st_size))
                except:
                    continue
            
            # Sort by size for efficient comparison
            remaining_with_sizes.sort(key=lambda x: x[1])
            
            for i in range(len(remaining_with_sizes)):
                for j in range(i + 1, len(remaining_with_sizes)):
                    file1, size1 = remaining_with_sizes[i]
                    file2, size2 = remaining_with_sizes[j]
                    
                    # If size difference is too large, break (since list is sorted)
                    if size2 > size1 * 1.05:  # More than 5% larger
                        break
                    
                    # Check if sizes are within 5% of each other
                    if abs(size1 - size2) / max(size1, size2) <= 0.05:
                        pair = tuple(sorted([file1, file2]))
                        if pair not in processed_pairs:
                            self.duplicates.append({
                                'type': 'Similar Size',
                                'file1': file1,
                                'file2': file2,
                                'reason': f'Images have similar file sizes: {size1/1024:.1f}KB vs {size2/1024:.1f}KB'
                            })
                            processed_pairs.add(pair)
            
            self.root.after(0, self.scan_completed)
            
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", f"Error during scan: {e}"))
            self.root.after(0, self.scan_completed)
    
    def calculate_file_hash(self, file_path, chunk_size=8192):
        try:
            hash_md5 = hashlib.md5()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(chunk_size), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except (IOError, OSError):
            return None
    
    def get_image_dimensions(self, file_path):
        if not PIL_AVAILABLE:
            return None
        
        try:
            with Image.open(file_path) as img:
                return img.size  # Returns (width, height)
        except Exception:
            return None
    
    def get_image_info(self, file_path):
        try:
            stat = os.stat(file_path)
            size_mb = stat.st_size / (1024 * 1024)
            size_kb = stat.st_size / 1024
            mod_time = time.ctime(stat.st_mtime)
            
            info = f"Path: {file_path}\n\n"
            info += f"Filename: {os.path.basename(file_path)}\n"
            info += f"Size: {size_mb:.2f} MB ({size_kb:.1f} KB)\n"
            info += f"Modified: {mod_time}\n"
            info += f"Directory: {os.path.dirname(file_path)}\n\n"
            
            # Add image-specific info
            if PIL_AVAILABLE:
                try:
                    with Image.open(file_path) as img:
                        info += "=== IMAGE INFO ===\n"
                        info += f"Dimensions: {img.size[0]} x {img.size[1]} pixels\n"
                        info += f"Format: {img.format}\n"
                        info += f"Mode: {img.mode}\n"
                        
                        # Calculate megapixels
                        megapixels = (img.size[0] * img.size[1]) / 1000000
                        info += f"Megapixels: {megapixels:.2f} MP\n"
                        
                        # Add EXIF data if available
                        if hasattr(img, '_getexif') and img._getexif():
                            exif = img._getexif()
                            if exif:
                                info += "\n=== EXIF DATA ===\n"
                                # Common EXIF tags
                                exif_tags = {
                                    36867: 'Date Taken',
                                    272: 'Camera Model',
                                    271: 'Camera Make',
                                    34855: 'ISO Speed',
                                    37377: 'Shutter Speed',
                                    37378: 'Aperture',
                                    37386: 'Focal Length'
                                }
                                
                                for tag_id, tag_name in exif_tags.items():
                                    if tag_id in exif:
                                        value = exif[tag_id]
                                        info += f"{tag_name}: {value}\n"
                        
                except Exception as e:
                    info += f"Error reading image info: {e}\n"
            else:
                info += "PIL not available - install with: pip install Pillow\n"
            
            return info
        except Exception as e:
            return f"Error reading file info: {e}"
    
    def load_image_preview(self, file_path, max_size=(300, 200)):
        if not PIL_AVAILABLE:
            return None
        
        try:
            with Image.open(file_path) as img:
                # Convert to RGB if needed (handles RGBA, P, etc.)
                if img.mode not in ('RGB', 'L'):
                    img = img.convert('RGB')
                
                # Calculate size maintaining aspect ratio
                img_ratio = img.size[0] / img.size[1]
                max_ratio = max_size[0] / max_size[1]
                
                if img_ratio > max_ratio:
                    # Image is wider
                    new_width = max_size[0]
                    new_height = int(max_size[0] / img_ratio)
                else:
                    # Image is taller
                    new_height = max_size[1]
                    new_width = int(max_size[1] * img_ratio)
                
                img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                return ImageTk.PhotoImage(img_resized)
        except Exception as e:
            return None
    
    def scan_completed(self):
        self.progress.stop()
        self.scan_btn.config(state='normal')
        
        total_message = ""
        if hasattr(self, 'auto_deleted_count') and self.auto_deleted_count > 0:
            total_message = f"Auto-deleted {self.auto_deleted_count} identical images. "
        
        if self.duplicates:
            self.status_var.set(f"{total_message}Found {len(self.duplicates)} image pairs for review")
            self.current_duplicate_index = 0
            self.show_current_duplicate()
            self.next_btn.config(state='normal' if len(self.duplicates) > 1 else 'disabled')
            self.prev_btn.config(state='disabled')
        else:
            if hasattr(self, 'auto_deleted_count') and self.auto_deleted_count > 0:
                self.status_var.set(f"{total_message}No additional duplicates found")
                self.duplicate_info.set(f"Auto-deleted {self.auto_deleted_count} identical images")
            else:
                self.status_var.set("No duplicates found")
                self.duplicate_info.set("No duplicates found")
            self.clear_displays()
    
    def show_current_duplicate(self):
        if not self.duplicates or self.current_duplicate_index >= len(self.duplicates):
            return
        
        duplicate = self.duplicates[self.current_duplicate_index]
        self.duplicate_info.set(f"Duplicate {self.current_duplicate_index + 1} of {len(self.duplicates)} ({duplicate['type']})")
        
        # Load and display images
        file1_path = duplicate['file1']
        file2_path = duplicate['file2']
        
        # Load image previews
        img1 = self.load_image_preview(file1_path)
        img2 = self.load_image_preview(file2_path)
        
        if img1:
            self.left_image_label.configure(image=img1, text="")
            self.left_image_label.image = img1  # Keep a reference
        else:
            self.left_image_label.configure(image="", text="Cannot load image")
            self.left_image_label.image = None
        
        if img2:
            self.right_image_label.configure(image=img2, text="")
            self.right_image_label.image = img2  # Keep a reference
        else:
            self.right_image_label.configure(image="", text="Cannot load image")
            self.right_image_label.image = None
        
        # Display file info
        self.left_text.delete(1.0, tk.END)
        file1_info = self.get_image_info(file1_path)
        self.left_text.insert(tk.END, file1_info)
        
        self.right_text.delete(1.0, tk.END)
        file2_info = self.get_image_info(file2_path)
        self.right_text.insert(tk.END, file2_info)
    
    def clear_displays(self):
        self.left_text.delete(1.0, tk.END)
        self.right_text.delete(1.0, tk.END)
        self.left_image_label.configure(image="", text="No image")
        self.right_image_label.configure(image="", text="No image")
        self.left_image_label.image = None
        self.right_image_label.image = None
    
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
        messagebox.showinfo("Keep Both", "Both images will be kept. Moving to next duplicate pair.")
        self.move_to_next_duplicate()
    
    def skip_pair(self):
        self.move_to_next_duplicate()
    
    def delete_file_and_continue(self, file_to_delete):
        if not self.duplicates:
            return
            
        duplicate = self.duplicates[self.current_duplicate_index]
        file_path = duplicate[file_to_delete]
        filename = os.path.basename(file_path)
        
        try:
            os.remove(file_path)
            messagebox.showinfo("Deleted", f"Image deleted: {filename}")
            self.move_to_next_duplicate()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to delete image:\n{e}")
    
    def move_to_next_duplicate(self):
        if self.duplicates and self.current_duplicate_index < len(self.duplicates):
            self.duplicates.pop(self.current_duplicate_index)
        
        if self.current_duplicate_index >= len(self.duplicates):
            self.current_duplicate_index = len(self.duplicates) - 1
        
        if self.duplicates:
            self.show_current_duplicate()
            self.update_navigation_buttons()
        else:
            self.status_var.set("All duplicates processed!")
            self.duplicate_info.set("All duplicates processed!")
            self.clear_displays()
            self.prev_btn.config(state='disabled')
            self.next_btn.config(state='disabled')

def main():
    print("Starting Image Duplicate Finder...")
    
    try:
        print("Creating application...")
        root = tk.Tk()
        app = ImageDuplicateFinder(root)
        
        if not PIL_AVAILABLE:
            messagebox.showinfo("Info", 
                "PIL (Pillow) library not found. Image preview and advanced features will be disabled.\n\n" +
                "To install: pip install Pillow\n\n" +
                "The program will still work for basic duplicate detection.")
        
        print("Starting GUI...")
        root.mainloop()
        print("Program ended normally.")
        
    except Exception as e:
        print(f"Error starting application: {e}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        input("Press Enter to exit...")

if __name__ == "__main__":
    main()