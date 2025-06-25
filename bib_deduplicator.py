#!/usr/bin/env python3
"""
BibTeX Deduplicator - GUI Version

This application detects and removes duplicate entries from .bib files,
providing a visual interface for selecting which duplicates to keep.
"""

import re
import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
from difflib import SequenceMatcher
import threading
from queue import Queue
import argparse  # Added missing import for command line mode

class BibDedupGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("BibTeX Deduplicator")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)
        
        # Variables
        self.input_file = tk.StringVar()
        self.output_file = tk.StringVar()
        self.status = tk.StringVar(value="Ready")
        self.progress_value = tk.DoubleVar(value=0.0)
        self.entries = []
        self.entries_info = []
        self.duplicates = []
        self.entries_to_keep = []
        self.current_duplicate_idx = 0
        self.selected_entry = tk.IntVar(value=0)
        self.stop_requested = False
        
        # Configuration options
        self.similarity_threshold = tk.DoubleVar(value=0.8)
        self.threshold_label = tk.StringVar(value="0.80")  # Fixed: Added a separate StringVar for the label
        
        # Message queue for thread communication
        self.queue = Queue()
        
        # Console Text Widget for logging
        self.console_text = None
        
        # Create UI
        self._create_ui()
        
        # Check for messages from worker thread
        self.root.after(100, self._check_queue)
        
        # Redirect stdout to our console widget
        self.stdout_original = sys.stdout
        sys.stdout = self
        
        # Setup threshold update callback
        self.similarity_threshold.trace_add("write", self._update_threshold_label)
    
    def _update_threshold_label(self, *args):
        """Update the threshold label when the slider changes."""
        self.threshold_label.set(f"{self.similarity_threshold.get():.2f}")
    
    def _create_ui(self):
        """Create the user interface."""
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Style configuration
        style = ttk.Style()
        style.configure('TButton', font=('Helvetica', 11))
        style.configure('TLabel', font=('Helvetica', 11))
        style.configure('Header.TLabel', font=('Helvetica', 12, 'bold'))
        style.configure('Status.TLabel', font=('Helvetica', 10, 'italic'))
        
        # Notebook for tabs
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Tab 1: Main functionality
        main_tab = ttk.Frame(notebook)
        notebook.add(main_tab, text="Main")
        
        # Tab 2: Advanced Settings
        settings_tab = ttk.Frame(notebook)
        notebook.add(settings_tab, text="Settings")
        
        # Tab 3: Console Log
        console_tab = ttk.Frame(notebook)
        notebook.add(console_tab, text="Log")
        
        # Console log in tab 3
        console_frame = ttk.LabelFrame(console_tab, text="Console Output", padding="5")
        console_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.console_text = scrolledtext.ScrolledText(console_frame, wrap=tk.WORD, height=20)
        self.console_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Settings in tab 2
        settings_frame = ttk.LabelFrame(settings_tab, text="Detection Settings", padding="10")
        settings_frame.pack(fill=tk.BOTH, expand=False, padx=5, pady=5)
        
        ttk.Label(settings_frame, text="Title/Author Similarity Threshold:").grid(row=0, column=0, sticky=tk.W, pady=5)
        similarity_scale = ttk.Scale(
            settings_frame, 
            from_=0.6, 
            to=0.95, 
            variable=self.similarity_threshold, 
            orient=tk.HORIZONTAL, 
            length=200
        )
        similarity_scale.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=5)
        
        # Fixed: Use the separate StringVar for the threshold label
        ttk.Label(settings_frame, textvariable=self.threshold_label).grid(row=0, column=2, padx=5)
        
        # Main interface in tab 1
        
        # File selection frame
        file_frame = ttk.LabelFrame(main_tab, text="File Selection", padding="10")
        file_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(file_frame, text="Input BibTeX File:").grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Entry(file_frame, textvariable=self.input_file, width=50).grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)
        ttk.Button(file_frame, text="Browse...", command=self._browse_input).grid(row=0, column=2, padx=5, pady=5)
        
        ttk.Label(file_frame, text="Output BibTeX File:").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Entry(file_frame, textvariable=self.output_file, width=50).grid(row=1, column=1, padx=5, pady=5, sticky=tk.EW)
        ttk.Button(file_frame, text="Browse...", command=self._browse_output).grid(row=1, column=2, padx=5, pady=5)
        
        button_frame = ttk.Frame(file_frame)
        button_frame.grid(row=2, column=0, columnspan=3, pady=10)
        
        ttk.Button(button_frame, text="Start Analysis", command=self._start_analysis).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Stop Processing", command=self._stop_processing).pack(side=tk.LEFT, padx=5)
        
        # Progress frame
        progress_frame = ttk.Frame(main_tab, padding="5")
        progress_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(progress_frame, text="Status:").pack(side=tk.LEFT, padx=5)
        ttk.Label(progress_frame, textvariable=self.status, style="Status.TLabel").pack(side=tk.LEFT, padx=5)
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_value, length=200, mode='determinate')
        self.progress_bar.pack(side=tk.RIGHT, padx=5)
        
        # Duplicate resolution frame (initially hidden)
        self.dup_frame = ttk.LabelFrame(main_tab, text="Duplicate Resolution", padding="10")
        
        ttk.Label(self.dup_frame, text="Select which entry to keep:", style="Header.TLabel").grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        self.group_label = ttk.Label(self.dup_frame, text="Group 0 of 0")
        self.group_label.grid(row=1, column=0, sticky=tk.W, pady=5)
        
        # Radio button frame for selection
        self.radio_frame = ttk.Frame(self.dup_frame)
        self.radio_frame.grid(row=2, column=0, columnspan=2, sticky=tk.EW, pady=5)
        
        # Comparison frame - two text widgets side by side
        compare_frame = ttk.Frame(self.dup_frame)
        compare_frame.grid(row=3, column=0, columnspan=2, sticky=tk.NSEW, pady=5)
        
        # Left entry viewer
        left_frame = ttk.LabelFrame(compare_frame, text="Selected Entry")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        self.entry_text = scrolledtext.ScrolledText(left_frame, wrap=tk.WORD, width=40, height=15)
        self.entry_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Button frame
        button_frame = ttk.Frame(self.dup_frame)
        button_frame.grid(row=4, column=0, columnspan=2, sticky=tk.EW, pady=10)
        
        ttk.Button(button_frame, text="Keep Selected", command=self._keep_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Keep All in Group", command=self._keep_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Skip Group", command=self._next_duplicate).pack(side=tk.RIGHT, padx=5)
        
        # Set weight for resizing
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(0, weight=1)
        self.dup_frame.columnconfigure(0, weight=1)
        self.dup_frame.rowconfigure(3, weight=1)
        
        # Set initial focus
        self.root.focus_set()
    
    # Stdout redirection methods
    def write(self, text):
        """Write to the console widget."""
        if self.console_text:
            self.console_text.insert(tk.END, text)
            self.console_text.see(tk.END)
        # Also write to the original stdout
        self.stdout_original.write(text)
    
    def flush(self):
        """Required for stdout redirection."""
        self.stdout_original.flush()
        
    def _stop_processing(self):
        """Request to stop current processing."""
        self.stop_requested = True
        self.status.set("Stop requested - finishing current task...")
        print("Stop requested by user. Waiting for current task to complete...")
    
    def _browse_input(self):
        """Browse for input BibTeX file."""
        filename = filedialog.askopenfilename(
            title="Select BibTeX File",
            filetypes=[("BibTeX Files", "*.bib"), ("All Files", "*.*")]
        )
        if filename:
            self.input_file.set(filename)
            # Auto-generate output filename
            base_name = os.path.splitext(filename)[0]
            self.output_file.set(f"{base_name}_deduplicated.bib")
    
    def _browse_output(self):
        """Browse for output BibTeX file."""
        filename = filedialog.asksaveasfilename(
            title="Save Deduplicated BibTeX File",
            defaultextension=".bib",
            filetypes=[("BibTeX Files", "*.bib"), ("All Files", "*.*")]
        )
        if filename:
            self.output_file.set(filename)
    
    def _start_analysis(self):
        """Start the analysis process in a separate thread."""
        input_file = self.input_file.get()
        output_file = self.output_file.get()
        
        if not input_file:
            messagebox.showerror("Error", "Please select an input BibTeX file.")
            return
        
        if not output_file:
            messagebox.showerror("Error", "Please specify an output BibTeX file.")
            return
        
        if not os.path.isfile(input_file):
            messagebox.showerror("Error", f"File '{input_file}' not found.")
            return
        
        # Reset state
        self.entries = []
        self.entries_info = []
        self.duplicates = []
        self.entries_to_keep = []
        self.current_duplicate_idx = 0
        self.stop_requested = False
        
        # Start worker thread
        threading.Thread(
            target=self._analysis_worker,
            args=(input_file, output_file),
            daemon=True
        ).start()
    
    def _analysis_worker(self, input_file, output_file):
        """Worker thread for analysis to avoid freezing UI."""
        try:
            # Update status
            self.queue.put(("status", "Parsing BibTeX file..."))
            self.queue.put(("progress", 0))
            
            # Parse entries
            self.entries = parse_bib_entries(input_file)
            self.queue.put(("status", f"Found {len(self.entries)} entries."))
            self.queue.put(("progress", 10))
            
            # Extract entry info
            self.queue.put(("status", "Extracting information from entries..."))
            total_entries = len(self.entries)
            self.entries_info = []
            
            for i, entry in enumerate(self.entries):
                self.entries_info.append(extract_entry_info(entry))
                progress = 10 + (i / total_entries) * 30
                self.queue.put(("progress", progress))
            
            valid_entries = sum(1 for e in self.entries_info if e is not None)
            self.queue.put(("status", f"Successfully parsed {valid_entries} entries."))
            self.queue.put(("progress", 40))
            
            # Find duplicates
            self.queue.put(("status", "Finding duplicate entries..."))
            # Pass the similarity threshold from the GUI
            self.duplicates = find_duplicates(self.entries_info, self.similarity_threshold.get())
            self.queue.put(("status", f"Found {len(self.duplicates)} potential duplicate groups."))
            self.queue.put(("progress", 80))
            
            if not self.duplicates:
                # No duplicates found
                self.queue.put(("status", "No duplicates found. Creating output file..."))
                entries_to_keep = [entry['full_entry'] for entry in self.entries_info if entry is not None]
                
                # Handle entries that couldn't be parsed
                for i, entry in enumerate(self.entries):
                    if self.entries_info[i] is None:
                        entries_to_keep.append(entry)
                
                write_output_file(entries_to_keep, output_file)
                self.queue.put(("progress", 100))
                self.queue.put(("status", f"Complete! Output written to {output_file}"))
                self.queue.put(("message", f"No duplicates found.\nOriginal file copied to {output_file}"))
            else:
                # Start duplicate resolution
                self.queue.put(("progress", 90))
                self.queue.put(("status", "Ready for duplicate resolution"))
                self.queue.put(("show_duplicates", None))
                
                # Identify entries to keep that aren't in duplicate groups
                for i, entry in enumerate(self.entries_info):
                    if entry is None:
                        self.entries_to_keep.append(self.entries[i])
                        continue
                        
                    if not any(i in group for group in self.duplicates):
                        self.entries_to_keep.append(entry['full_entry'])
                
        except Exception as e:
            self.queue.put(("error", str(e)))
    
    def _check_queue(self):
        """Check messages from worker thread."""
        try:
            while True:
                message, data = self.queue.get_nowait()
                
                if message == "status":
                    self.status.set(data)
                elif message == "progress":
                    self.progress_value.set(data)
                elif message == "show_duplicates":
                    self._show_duplicate_resolution()
                elif message == "message":
                    messagebox.showinfo("Information", data)
                elif message == "error":
                    messagebox.showerror("Error", data)
                    self.status.set("Error occurred")
                
                self.queue.task_done()
        except:
            # No more messages, check again later
            pass
        
        self.root.after(100, self._check_queue)
    
    def _show_duplicate_resolution(self):
        """Show the duplicate resolution interface."""
        self.dup_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self._show_current_duplicate()
    
    def _show_current_duplicate(self):
        """Show the current duplicate group for resolution."""
        if self.current_duplicate_idx >= len(self.duplicates):
            # All duplicates processed
            self._write_output_file()
            return
        
        # Clear previous radio buttons
        for widget in self.radio_frame.winfo_children():
            widget.destroy()
        
        # Update group label
        self.group_label.config(text=f"Group {self.current_duplicate_idx + 1} of {len(self.duplicates)}")
        
        # Get current duplicate group
        group = self.duplicates[self.current_duplicate_idx]
        
        # Check if entries are identical
        identical, best_idx = check_identical_entries(self.entries_info, group)
        if identical:
            # Automatically keep the best entry and move to next group
            print(f"Automatically selecting identical entry: {self.entries_info[best_idx]['citation_key']}")
            self.entries_to_keep.append(self.entries_info[best_idx]['full_entry'])
            self.current_duplicate_idx += 1
            self._show_current_duplicate()
            return
        
        # Reset selection
        self.selected_entry.set(0)
        
        # Add a label indicating these are not identical
        ttk.Label(
            self.radio_frame,
            text="These entries are similar but not identical:",
            style="Header.TLabel"
        ).grid(row=0, column=0, sticky=tk.W, pady=(0, 10))
        
        # Create radio buttons for each entry in the group
        for idx, entry_idx in enumerate(group):
            entry = self.entries_info[entry_idx]
            if entry is None:
                continue
                
            citation_key = entry['citation_key']
            title = entry['title'][:40] + "..." if len(entry['title']) > 40 else entry['title']
            year = entry['year']
            
            label_text = f"{citation_key} ({year}): {title}"
            
            radio = ttk.Radiobutton(
                self.radio_frame,
                text=label_text,
                variable=self.selected_entry,
                value=idx,
                command=self._update_entry_view
            )
            radio.grid(row=idx+1, column=0, sticky=tk.W, pady=2)
        
        # Initialize view with first entry
        self.selected_entry.set(0)
        self._update_entry_view()
    
    def _update_entry_view(self):
        """Update the entry view with the selected entry."""
        group = self.duplicates[self.current_duplicate_idx]
        selected_idx = self.selected_entry.get()
        
        if 0 <= selected_idx < len(group):
            entry_idx = group[selected_idx]
            entry = self.entries_info[entry_idx]
            
            if entry is not None:
                # Clear text
                self.entry_text.delete(1.0, tk.END)
                
                # Format the entry nicely
                self.entry_text.insert(tk.END, f"Citation Key: {entry['citation_key']}\n\n")
                self.entry_text.insert(tk.END, f"Entry Type: {entry['type']}\n\n")
                
                if entry['title']:
                    self.entry_text.insert(tk.END, f"Title: {entry['title']}\n\n")
                
                if entry['authors']:
                    self.entry_text.insert(tk.END, f"Authors: {entry['authors']}\n\n")
                
                if entry['year']:
                    self.entry_text.insert(tk.END, f"Year: {entry['year']}\n\n")
                
                if entry['doi']:
                    self.entry_text.insert(tk.END, f"DOI: {entry['doi']}\n\n")
                
                self.entry_text.insert(tk.END, "Full Entry:\n")
                self.entry_text.insert(tk.END, entry['full_entry'])
    
    def _keep_selected(self):
        """Keep the selected entry and move to next duplicate group."""
        group = self.duplicates[self.current_duplicate_idx]
        selected_idx = self.selected_entry.get()
        
        if 0 <= selected_idx < len(group):
            entry_idx = group[selected_idx]
            entry = self.entries_info[entry_idx]
            
            if entry is not None:
                self.entries_to_keep.append(entry['full_entry'])
        
        self.current_duplicate_idx += 1
        self._show_current_duplicate()
    
    def _keep_all(self):
        """Keep all entries in the current group and move to next duplicate group."""
        group = self.duplicates[self.current_duplicate_idx]
        
        for entry_idx in group:
            entry = self.entries_info[entry_idx]
            if entry is not None:
                self.entries_to_keep.append(entry['full_entry'])
        
        self.current_duplicate_idx += 1
        self._show_current_duplicate()
    
    def _next_duplicate(self):
        """Skip current duplicate group without keeping any entries."""
        self.current_duplicate_idx += 1
        self._show_current_duplicate()
    
    def _write_output_file(self):
        """Write the output file with deduplicated entries."""
        output_file = self.output_file.get()
        
        self.status.set("Writing output file...")
        self.progress_value.set(95)
        
        try:
            write_output_file(self.entries_to_keep, output_file)
            self.progress_value.set(100)
            self.status.set("Complete!")
            
            message = (
                f"Deduplication complete!\n\n"
                f"Original entries: {len(self.entries)}\n"
                f"Entries after deduplication: {len(self.entries_to_keep)}\n\n"
                f"Output written to:\n{output_file}"
            )
            messagebox.showinfo("Deduplication Complete", message)
            
            # Hide duplicate resolution frame
            self.dup_frame.pack_forget()
            
        except Exception as e:
            messagebox.showerror("Error", f"Error writing output file: {str(e)}")
            self.status.set("Error")


# BibTeX processing functions

def check_identical_entries(entries_info, group):
    """
    Check if entries in a group are identical (ignoring citation keys).
    Returns:
    - True and index of entry to keep if all entries are identical
    - False and None if not all entries are identical
    """
    if not group or len(group) <= 1:
        return False, None
    
    identical_entries = []
    primary_idx = group[0]
    primary_entry = entries_info[primary_idx]
    
    # Extract the content we want to compare (everything except citation key)
    primary_content = {
        'title': primary_entry['title'].lower() if primary_entry['title'] else '',
        'authors': primary_entry['authors'].lower() if primary_entry['authors'] else '',
        'year': primary_entry['year'],
        'doi': primary_entry['doi'].lower() if primary_entry['doi'] else '',
        'type': primary_entry['type'].lower() if primary_entry['type'] else ''
    }
    
    # Check all entries against the primary
    for idx in group[1:]:
        entry = entries_info[idx]
        entry_content = {
            'title': entry['title'].lower() if entry['title'] else '',
            'authors': entry['authors'].lower() if entry['authors'] else '',
            'year': entry['year'],
            'doi': entry['doi'].lower() if entry['doi'] else '',
            'type': entry['type'].lower() if entry['type'] else ''
        }
        
        # If any field doesn't match, entries are not identical
        if primary_content != entry_content:
            return False, None
    
    # All entries are identical - choose the one with the shortest citation key
    best_idx = group[0]
    best_key_len = len(entries_info[best_idx]['citation_key'])
    
    for idx in group[1:]:
        key_len = len(entries_info[idx]['citation_key'])
        if key_len < best_key_len:
            best_idx = idx
            best_key_len = key_len
    
    return True, best_idx

def parse_bib_entries(bib_file_path):
    """Parse a .bib file and extract individual entries."""
    with open(bib_file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # Find all entries - anything between @ and the next @ or end of file
    entry_pattern = r'@(.*?)((?=@)|$)'
    entries = re.finditer(entry_pattern, content, re.DOTALL)
    
    parsed_entries = []
    for entry in entries:
        entry_text = entry.group(0).strip()
        if entry_text:  # Skip empty matches
            parsed_entries.append(entry_text)
    
    return parsed_entries

def extract_entry_info(entry):
    """Extract key information from a BibTeX entry."""
    # Extract entry type and citation key
    match = re.match(r'@(\w+)\s*{\s*([^,]+)', entry)
    if not match:
        return None
    
    entry_type = match.group(1).lower()
    citation_key = match.group(2)
    
    # Extract title
    title_match = re.search(r'title\s*=\s*[{"](.+?)[}"]', entry, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).lower().replace('\n', ' ').replace('\t', ' ') if title_match else ""
    title = re.sub(r'\s+', ' ', title).strip()  # Normalize whitespace
    
    # Extract authors
    author_match = re.search(r'author\s*=\s*[{"](.+?)[}"]', entry, re.IGNORECASE | re.DOTALL)
    authors = author_match.group(1) if author_match else ""
    
    # Extract year
    year_match = re.search(r'year\s*=\s*[{"]?(\d{4})[}"]?', entry, re.IGNORECASE)
    year = year_match.group(1) if year_match else ""
    
    # Extract DOI
    doi_match = re.search(r'doi\s*=\s*[{"](.+?)[}"]', entry, re.IGNORECASE)
    doi = doi_match.group(1) if doi_match else ""
    
    return {
        'type': entry_type,
        'citation_key': citation_key,
        'title': title,
        'authors': authors,
        'year': year,
        'doi': doi,
        'full_entry': entry
    }

def find_duplicates(entries_info, similarity_threshold=0.8):
    """Find potential duplicate entries based on similarity."""
    duplicates = []
    processed = set()
    
    print(f"Finding duplicates among {len(entries_info)} entries...")
    print(f"Using similarity threshold: {similarity_threshold}")
    
    # Use a faster approach for large datasets
    total_entries = len(entries_info)
    for i, entry1 in enumerate(entries_info):
        if i % 10 == 0:  # Print progress every 10 entries
            print(f"Processing entry {i}/{total_entries}...")
        
        if i in processed:
            continue
            
        # Skip entries with parsing issues
        if entry1 is None:
            continue
            
        group = [i]
        
        # Create DOI lookup for faster matching
        if entry1['doi']:
            for j, entry2 in enumerate(entries_info):
                if i == j or j in processed or entry2 is None:
                    continue
                
                if entry1['doi'] == entry2['doi']:
                    group.append(j)
        
        # Only do the expensive similarity checks for entries without DOI matches
        if len(group) == 1:
            # Only compare with entries that have the same year (much faster filtering)
            same_year_indices = [j for j, entry2 in enumerate(entries_info) 
                               if entry2 is not None and j != i and j not in processed 
                               and entry2['year'] == entry1['year']]
            
            for j in same_year_indices:
                entry2 = entries_info[j]
                
                # High title similarity with matching year
                if entry1['title'] and entry2['title']:
                    # Quick pre-check to avoid expensive SequenceMatcher when possible
                    if abs(len(entry1['title']) - len(entry2['title'])) / max(len(entry1['title']), 1) < 0.3:
                        title_similarity = SequenceMatcher(None, entry1['title'], entry2['title']).ratio()
                        if title_similarity > similarity_threshold:
                            group.append(j)
                            continue
                
                # Only check authors if title didn't match
                if j not in group and entry1['authors'] and entry2['authors']:
                    # Quick pre-check
                    if abs(len(entry1['authors']) - len(entry2['authors'])) / max(len(entry1['authors']), 1) < 0.3:
                        authors_similarity = SequenceMatcher(None, entry1['authors'], entry2['authors']).ratio()
                        if authors_similarity > similarity_threshold:
                            group.append(j)
        
        # Found duplicates
        if len(group) > 1:
            # Add group and mark all entries as processed
            duplicates.append(group)
            processed.update(group)
    
    return duplicates

def write_output_file(entries, output_file):
    """Write the output file with the selected entries."""
    with open(output_file, 'w', encoding='utf-8') as file:
        for entry in entries:
            file.write(entry + "\n\n")


def main():
    """Main entry point for the application."""
    # Parse command line arguments
    print("Started arg parser")
    parser = argparse.ArgumentParser(description="BibTeX Deduplicator")
    parser.add_argument("-i", "--input", help="Input BibTeX file")
    parser.add_argument("-o", "--output", help="Output BibTeX file")
    parser.add_argument("-t", "--threshold", type=float, default=0.8,
                        help="Similarity threshold (default: 0.8)")
    parser.add_argument("--cli", action="store_true", 
                        help="Run in command line mode (no GUI)")
    args = parser.parse_args()
    
    # Command-line mode
    if args.cli:
        if not args.input or not args.output:
            print("Error: --input and --output are required in CLI mode")
            parser.print_help()
            return 1
        
        try:
            print(f"Parsing BibTeX file: {args.input}")
            entries = parse_bib_entries(args.input)
            print(f"Found {len(entries)} entries.")
            
            print("Extracting information from entries...")
            entries_info = []
            for entry in entries:
                entries_info.append(extract_entry_info(entry))
            
            valid_entries = sum(1 for e in entries_info if e is not None)
            print(f"Successfully parsed {valid_entries} entries.")
            
            print(f"Finding duplicate entries (threshold: {args.threshold})...")
            duplicates = find_duplicates(entries_info, args.threshold)
            print(f"Found {len(duplicates)} potential duplicate groups.")
            
            if not duplicates:
                print("No duplicates found. Creating output file...")
                entries_to_keep = [entry['full_entry'] for entry in entries_info if entry is not None]
                
                # Handle entries that couldn't be parsed
                for i, entry in enumerate(entries):
                    if entries_info[i] is None:
                        entries_to_keep.append(entry)
                
                write_output_file(entries_to_keep, args.output)
                print(f"Complete! Output written to {args.output}")
            else:
                print("\nDuplicate groups found:")
                entries_to_keep = []
                
                # Add entries that aren't in duplicate groups
                for i, entry in enumerate(entries_info):
                    if entry is None:
                        entries_to_keep.append(entries[i])
                        continue
                    
                    if not any(i in group for group in duplicates):
                        entries_to_keep.append(entry['full_entry'])
                
                # Process each duplicate group
                for i, group in enumerate(duplicates):
                    print(f"\nGroup {i+1} of {len(duplicates)}:")
                    
                    # Check for identical entries
                    identical, best_idx = check_identical_entries(entries_info, group)
                    if identical:
                        print(f"Entries are identical. Automatically keeping: {entries_info[best_idx]['citation_key']}")
                        entries_to_keep.append(entries_info[best_idx]['full_entry'])
                        continue
                    
                    # List entries in this group
                    for j, entry_idx in enumerate(group):
                        entry = entries_info[entry_idx]
                        if entry is None:
                            continue
                        print(f"{j+1}. {entry['citation_key']} ({entry['year']}): {entry['title'][:60]}...")
                    
                    # In CLI mode, we'll just keep the first entry in each group
                    print("Keeping first entry in CLI mode.")
                    entry_idx = group[0]
                    entries_to_keep.append(entries_info[entry_idx]['full_entry'])
                
                # Write output file
                print(f"\nWriting output file: {args.output}")
                write_output_file(entries_to_keep, args.output)
                print(f"Complete! {len(entries_to_keep)} entries saved.")
            
            return 0
        
        except Exception as e:
            print(f"Error: {str(e)}")
            return 1
    
    # GUI mode
    else:
        root = tk.Tk()
        app = BibDedupGUI(root)
        
        # If input and output files specified, set them in the GUI
        if args.input:
            app.input_file.set(args.input)
        if args.output:
            app.output_file.set(args.output)
        if args.threshold:
            app.similarity_threshold.set(args.threshold)
        
        root.mainloop()
        return 0


if __name__ == "__main__":
    sys.exit(main())