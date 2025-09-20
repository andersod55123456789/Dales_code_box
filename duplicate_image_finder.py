#!/usr/bin/env python3
"""
Duplicate Image Eliminator
This script finds and removes duplicate images from specified directories.
Uses perceptual hashing to detect duplicates even with minor differences.
"""

import os
import hashlib
from collections import defaultdict
from PIL import Image
import imagehash
import argparse
import sys
from pathlib import Path

class DuplicateImageFinder:
    def __init__(self, directories, similarity_threshold=5, dry_run=True):
        self.directories = directories
        self.similarity_threshold = similarity_threshold
        self.dry_run = dry_run
        self.supported_formats = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp'}
        self.image_hashes = defaultdict(list)
        self.duplicates_found = []
        
    def get_file_hash(self, filepath):
        """Generate MD5 hash of file content for exact duplicates"""
        hash_md5 = hashlib.md5()
        try:
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            print(f"Error hashing {filepath}: {e}")
            return None
    
    def get_image_hash(self, filepath):
        """Generate perceptual hash of image for similar image detection"""
        try:
            with Image.open(filepath) as img:
                # Convert to RGB if necessary
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                # Use average hash for good performance and accuracy
                return imagehash.average_hash(img)
        except Exception as e:
            print(f"Error processing image {filepath}: {e}")
            return None
    
    def find_images(self):
        """Find all images in specified directories"""
        image_files = []
        
        for directory in self.directories:
            directory_path = Path(directory)
            if not directory_path.exists():
                print(f"Warning: Directory {directory} does not exist")
                continue
                
            print(f"Scanning directory: {directory}")
            
            for root, dirs, files in os.walk(directory_path):
                for file in files:
                    file_path = Path(root) / file
                    if file_path.suffix.lower() in self.supported_formats:
                        image_files.append(str(file_path))
        
        print(f"Found {len(image_files)} image files")
        return image_files
    
    def find_exact_duplicates(self, image_files):
        """Find exact duplicates using file hashes"""
        print("\nFinding exact duplicates...")
        file_hashes = defaultdict(list)
        
        for filepath in image_files:
            file_hash = self.get_file_hash(filepath)
            if file_hash:
                file_hashes[file_hash].append(filepath)
        
        exact_duplicates = []
        for hash_value, files in file_hashes.items():
            if len(files) > 1:
                # Keep the first file, mark others as duplicates
                exact_duplicates.extend(files[1:])
                print(f"Exact duplicates found: {files}")
        
        return exact_duplicates
    
    def find_similar_duplicates(self, image_files):
        """Find similar images using perceptual hashing"""
        print("\nFinding similar duplicates...")
        similar_duplicates = []
        processed_hashes = []
        
        for i, filepath in enumerate(image_files):
            if i % 100 == 0:
                print(f"Processing image {i+1}/{len(image_files)}")
            
            img_hash = self.get_image_hash(filepath)
            if img_hash is None:
                continue
            
            # Check against already processed images
            for existing_hash, existing_file in processed_hashes:
                hash_diff = img_hash - existing_hash
                if hash_diff <= self.similarity_threshold:
                    similar_duplicates.append(filepath)
                    print(f"Similar images found (diff: {hash_diff}): {existing_file} <-> {filepath}")
                    break
            else:
                # No similar image found, add to processed list
                processed_hashes.append((img_hash, filepath))
        
        return similar_duplicates
    
    def remove_duplicates(self, duplicates):
        """Remove duplicate files"""
        if not duplicates:
            print("No duplicates to remove.")
            return
        
        print(f"\nFound {len(duplicates)} duplicate files")
        
        if self.dry_run:
            print("DRY RUN MODE - Files that would be deleted:")
            for duplicate in duplicates:
                print(f"  {duplicate}")
        else:
            print("Removing duplicate files...")
            removed_count = 0
            for duplicate in duplicates:
                try:
                    os.remove(duplicate)
                    print(f"Removed: {duplicate}")
                    removed_count += 1
                except Exception as e:
                    print(f"Error removing {duplicate}: {e}")
            
            print(f"Successfully removed {removed_count} duplicate files")
    
    def run(self):
        """Main execution method"""
        print("Duplicate Image Eliminator")
        print("=" * 50)
        
        # Find all image files
        image_files = self.find_images()
        if not image_files:
            print("No image files found.")
            return
        
        # Find exact duplicates
        exact_duplicates = self.find_exact_duplicates(image_files)
        
        # Remove exact duplicates from the list for similarity checking
        remaining_files = [f for f in image_files if f not in exact_duplicates]
        
        # Find similar duplicates
        similar_duplicates = self.find_similar_duplicates(remaining_files)
        
        # Combine all duplicates
        all_duplicates = exact_duplicates + similar_duplicates
        
        # Remove duplicates
        self.remove_duplicates(all_duplicates)
        
        # Summary
        print(f"\nSummary:")
        print(f"Total images scanned: {len(image_files)}")
        print(f"Exact duplicates found: {len(exact_duplicates)}")
        print(f"Similar duplicates found: {len(similar_duplicates)}")
        print(f"Total duplicates: {len(all_duplicates)}")

def main():
    parser = argparse.ArgumentParser(description="Find and remove duplicate images")
    parser.add_argument("directories", nargs="+", help="Directories to scan for images")
    parser.add_argument("--threshold", "-t", type=int, default=5, 
                       help="Similarity threshold (0-64, lower = more similar)")
    parser.add_argument("--execute", "-e", action="store_true", 
                       help="Actually delete files (default is dry run)")
    
    args = parser.parse_args()
    
    # Validate directories
    for directory in args.directories:
        if not os.path.exists(directory):
            print(f"Error: Directory '{directory}' does not exist")
            sys.exit(1)
    
    # Create and run the duplicate finder
    finder = DuplicateImageFinder(
        directories=args.directories,
        similarity_threshold=args.threshold,
        dry_run=not args.execute
    )
    
    finder.run()

if __name__ == "__main__":
    main()
